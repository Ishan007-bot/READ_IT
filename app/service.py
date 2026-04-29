"""High-level service that wires ingestion, retrieval, and the agent.

Both the Streamlit UI and the FastAPI endpoint go through this layer so
they share identical behaviour and can be tested in isolation.
"""
from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from app.agent import AgentResponse, PDFAgent
from app.config import UPLOAD_DIR, get_settings
from app.ingest import ingest_pdf
from app.retriever import HybridRetriever


@dataclass
class DocumentInfo:
    doc_id: str
    filename: str
    num_pages: int
    num_chunks: int


class PDFService:
    """Thread-safe-enough singleton for in-process apps."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._docs: Dict[str, DocumentInfo] = {}
        self._retrievers: Dict[str, HybridRetriever] = {}

    # ---- ingestion --------------------------------------------------------
    @staticmethod
    def _hash_file(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()[:16]

    def ingest(self, source_path: Path, original_name: str) -> DocumentInfo:
        doc_id = self._hash_file(source_path)
        target = UPLOAD_DIR / f"{doc_id}.pdf"
        if not target.exists():
            shutil.copyfile(source_path, target)

        retriever = HybridRetriever(doc_id, self.settings.embedding_model)
        if not retriever.load():
            chunks = ingest_pdf(target)
            retriever.build(chunks)

        info = DocumentInfo(
            doc_id=doc_id,
            filename=original_name,
            num_pages=retriever.num_pages,
            num_chunks=retriever.num_chunks,
        )
        self._docs[doc_id] = info
        self._retrievers[doc_id] = retriever
        return info

    # ---- chat -------------------------------------------------------------
    def chat(
        self,
        doc_id: str,
        question: str,
        history: List[dict] | None = None,
    ) -> AgentResponse:
        if doc_id not in self._retrievers:
            # Lazy reload from disk
            retriever = HybridRetriever(doc_id, self.settings.embedding_model)
            if not retriever.load():
                raise KeyError(f"Unknown doc_id: {doc_id}")
            self._retrievers[doc_id] = retriever
            self._docs[doc_id] = DocumentInfo(
                doc_id=doc_id,
                filename=f"{doc_id}.pdf",
                num_pages=retriever.num_pages,
                num_chunks=retriever.num_chunks,
            )
        agent = PDFAgent(self._retrievers[doc_id], self.settings)
        return agent.chat(question, history=history)

    # ---- introspection ----------------------------------------------------
    def get_doc(self, doc_id: str) -> DocumentInfo | None:
        return self._docs.get(doc_id)

    def list_docs(self) -> List[DocumentInfo]:
        return list(self._docs.values())


_service: PDFService | None = None


def get_service() -> PDFService:
    global _service
    if _service is None:
        _service = PDFService()
    return _service
