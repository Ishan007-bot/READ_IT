"""Offline tests for ingestion + retrieval. No API key needed."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.ingest import ingest_pdf
from app.retriever import HybridRetriever


SAMPLE = Path(__file__).parent / "fixtures" / "sample.pdf"


@pytest.fixture(scope="module")
def retriever() -> HybridRetriever:
    chunks = ingest_pdf(SAMPLE)
    r = HybridRetriever("test_offline", "sentence-transformers/all-MiniLM-L6-v2")
    r.build(chunks)
    return r


def test_chunks_have_pages():
    chunks = ingest_pdf(SAMPLE)
    assert len(chunks) >= 1
    pages = {c.page for c in chunks}
    assert pages.issubset(set(range(1, 7)))
    assert all(c.text for c in chunks)


def test_factual_query_finds_correct_page(retriever: HybridRetriever):
    hits = retriever.search("wheel encoder drift incident count", top_k=4)
    assert hits[0].chunk.page == 4
    assert hits[0].score > 0.3


def test_financial_query_finds_correct_page(retriever: HybridRetriever):
    hits = retriever.search("total revenue from R-7 sales", top_k=4)
    assert hits[0].chunk.page == 5
    assert hits[0].score > 0.3


def test_out_of_scope_query_has_low_score(retriever: HybridRetriever):
    hits = retriever.search("What is the capital of France?", top_k=4)
    assert hits[0].score < 0.25, (
        f"Out-of-scope query scored {hits[0].score:.3f} — this would let the "
        "agent answer from training data instead of refusing."
    )


def test_persistence_round_trip():
    chunks = ingest_pdf(SAMPLE)
    r1 = HybridRetriever("test_persist", "sentence-transformers/all-MiniLM-L6-v2")
    r1.build(chunks)

    r2 = HybridRetriever("test_persist", "sentence-transformers/all-MiniLM-L6-v2")
    assert r2.load() is True
    hits = r2.search("payload capacity", top_k=2)
    assert hits[0].chunk.page == 2
