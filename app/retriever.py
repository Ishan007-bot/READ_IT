"""Hybrid retriever: dense (FAISS) + sparse (BM25) with reciprocal rank fusion."""
from __future__ import annotations

import json
import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

import numpy as np

from app.config import INDEX_DIR
from app.ingest import Chunk


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@dataclass
class RetrievedChunk:
    chunk: Chunk
    score: float

    def to_dict(self) -> dict:
        d = self.chunk.to_dict()
        d["score"] = round(self.score, 4)
        return d


class HybridRetriever:
    """Builds and queries a hybrid index over a list of Chunks.

    Persisted artefacts under data/index/<doc_id>/:
        - chunks.json      ordered chunk metadata
        - embeddings.npy   normalised dense embeddings
        - faiss.index      FAISS inner-product index
        - bm25.pkl         pickled BM25 corpus
    """

    def __init__(self, doc_id: str, embedding_model_name: str):
        self.doc_id = doc_id
        self.embedding_model_name = embedding_model_name
        self.dir = INDEX_DIR / doc_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._chunks: List[Chunk] = []
        self._embeddings: np.ndarray | None = None
        self._faiss = None
        self._bm25 = None
        self._embedder = None

    # ---- internals --------------------------------------------------------
    def _embedder_lazy(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(self.embedding_model_name)
        return self._embedder

    def _embed(self, texts: list[str]) -> np.ndarray:
        model = self._embedder_lazy()
        vecs = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vecs.astype("float32")

    # ---- build ------------------------------------------------------------
    def build(self, chunks: List[Chunk]) -> None:
        import faiss
        from rank_bm25 import BM25Okapi

        if not chunks:
            raise ValueError("No chunks to index — PDF appears empty.")

        self._chunks = chunks
        texts = [c.text for c in chunks]
        emb = self._embed(texts)
        self._embeddings = emb

        index = faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)
        self._faiss = index

        tokenised = [_tokenize(t) for t in texts]
        self._bm25 = BM25Okapi(tokenised)

        self._persist()

    def _persist(self) -> None:
        import faiss

        with open(self.dir / "chunks.json", "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in self._chunks], f, ensure_ascii=False)
        np.save(self.dir / "embeddings.npy", self._embeddings)
        faiss.write_index(self._faiss, str(self.dir / "faiss.index"))
        with open(self.dir / "bm25.pkl", "wb") as f:
            pickle.dump(self._bm25, f)

    # ---- load -------------------------------------------------------------
    def load(self) -> bool:
        import faiss

        chunks_path = self.dir / "chunks.json"
        if not chunks_path.exists():
            return False
        with open(chunks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._chunks = [Chunk(**c) for c in data]
        self._embeddings = np.load(self.dir / "embeddings.npy")
        self._faiss = faiss.read_index(str(self.dir / "faiss.index"))
        with open(self.dir / "bm25.pkl", "rb") as f:
            self._bm25 = pickle.load(f)
        return True

    # ---- query ------------------------------------------------------------
    def search(self, query: str, top_k: int = 6) -> List[RetrievedChunk]:
        if self._faiss is None or self._bm25 is None:
            raise RuntimeError("Retriever is not built or loaded.")

        # Dense
        q_vec = self._embed([query])
        k_dense = min(top_k * 3, len(self._chunks))
        dense_scores, dense_idx = self._faiss.search(q_vec, k_dense)
        dense_idx = dense_idx[0].tolist()
        dense_scores = dense_scores[0].tolist()

        # Sparse
        bm25_scores = self._bm25.get_scores(_tokenize(query))
        sparse_idx = list(np.argsort(bm25_scores)[::-1][: top_k * 3])

        # RRF fusion
        rrf_k = 60
        fused: dict[int, float] = {}
        for rank, idx in enumerate(dense_idx):
            if idx < 0:
                continue
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (rrf_k + rank)
        for rank, idx in enumerate(sparse_idx):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (rrf_k + rank)

        # Use dense cosine as the "confidence" we report (more interpretable
        # than RRF for thresholding out-of-scope queries).
        dense_lookup = {idx: s for idx, s in zip(dense_idx, dense_scores) if idx >= 0}

        ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        out: List[RetrievedChunk] = []
        for idx, _ in ranked:
            confidence = dense_lookup.get(idx, 0.0)
            out.append(RetrievedChunk(chunk=self._chunks[idx], score=float(confidence)))
        return out

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    @property
    def num_pages(self) -> int:
        if not self._chunks:
            return 0
        return max(c.page for c in self._chunks)
