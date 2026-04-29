"""End-to-end agent tests. Requires GROQ_API_KEY in the environment.

These tests exercise the full pipeline: PDF -> chunks -> hybrid retrieval ->
Groq tool-calling -> citation enforcement -> structured response.

Run:
    pytest tests/test_agent.py -v -s

The 5 valid + 3 invalid query suite required by the assignment is in
TEST_CASES below.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from app.agent import CITATION_RE, PDFAgent
from app.config import get_settings
from app.ingest import ingest_pdf
from app.retriever import HybridRetriever


SAMPLE = Path(__file__).parent / "fixtures" / "sample.pdf"

pytestmark = pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live agent tests.",
)


@pytest.fixture(scope="module")
def agent() -> PDFAgent:
    settings = get_settings()
    chunks = ingest_pdf(SAMPLE)
    r = HybridRetriever("test_agent_e2e", settings.embedding_model)
    r.build(chunks)
    return PDFAgent(r, settings)


# ─────────────────────────────────────────────────────────────────────────────
# 5 valid queries — must produce grounded answers with citations
# ─────────────────────────────────────────────────────────────────────────────
VALID_CASES = [
    {
        "id": "valid-1-uptime",
        "question": "What was the average uptime of the R-7 in FY2025?",
        "must_contain_any": ["97.2", "97.2%"],
        "expected_pages": {1},
    },
    {
        "id": "valid-2-failure-mode",
        "question": "What is the most common failure mode and how many incidents did it cause?",
        "must_contain_any": ["wheel-encoder", "wheel encoder"],
        "must_also_contain_any": ["233", "38"],
        "expected_pages": {1, 4},
    },
    {
        "id": "valid-3-payload",
        "question": "What is the payload capacity of the R-7?",
        "must_contain_any": ["250 kg", "250kg"],
        "expected_pages": {2},
    },
    {
        "id": "valid-4-largest-deployment",
        "question": "Which is the largest single deployment and how many units does it have?",
        "must_contain_any": ["Memphis", "Operator Logistics"],
        "must_also_contain_any": ["312"],
        "expected_pages": {3},
    },
    {
        "id": "valid-5-revenue",
        "question": "What was the total revenue in FY2025 and the gross margin on hardware?",
        "must_contain_any": ["184.6"],
        "must_also_contain_any": ["34.2"],
        "expected_pages": {5},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 3 invalid / out-of-scope queries — must be refused
# ─────────────────────────────────────────────────────────────────────────────
INVALID_CASES = [
    {
        "id": "invalid-1-general-knowledge",
        "question": "What is the capital of France?",
        "reason": "general knowledge unrelated to the document",
    },
    {
        "id": "invalid-2-creative",
        "question": "Write me a short poem about robots.",
        "reason": "creative request outside document scope",
    },
    {
        "id": "invalid-3-related-but-absent",
        "question": "What is the R-7's network protocol stack and exact TCP port assignments?",
        "reason": "topic-adjacent but not actually in the document",
    },
]


def _has_citation(text: str) -> bool:
    return bool(CITATION_RE.search(text))


def _cited_pages(text: str) -> set[int]:
    pages: set[int] = set()
    for m in re.finditer(r"\[p\.?\s*(\d+)(?:\s*[–-]\s*(\d+))?\]", text, re.IGNORECASE):
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        pages.update(range(a, b + 1))
    return pages


REFUSAL_MARKERS = (
    "outside the scope",
    "couldn't find that",
    "could not find that",
    "i couldn't find",
    "i could not find",
)


def _is_refusal(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in REFUSAL_MARKERS)


@pytest.mark.parametrize("case", VALID_CASES, ids=[c["id"] for c in VALID_CASES])
def test_valid_query_is_grounded_and_cited(agent: PDFAgent, case: dict):
    resp = agent.chat(case["question"])
    print(f"\n[{case['id']}] {case['question']}\n-> {resp.answer.encode('ascii', 'replace').decode('ascii')}\n")

    assert resp.refused is False, f"Agent refused a valid question: {resp.answer}"
    assert _has_citation(resp.answer), "Answer is missing [p. N] citation"

    low = resp.answer.lower()
    assert any(s.lower() in low for s in case["must_contain_any"]), (
        f"Answer missing required content {case['must_contain_any']}: {resp.answer}"
    )
    if "must_also_contain_any" in case:
        assert any(s.lower() in low for s in case["must_also_contain_any"]), (
            f"Answer missing secondary content {case['must_also_contain_any']}: {resp.answer}"
        )

    cited = _cited_pages(resp.answer)
    assert cited & case["expected_pages"], (
        f"Cited pages {cited} do not overlap expected {case['expected_pages']}"
    )

    assert resp.tool_calls >= 1, "Agent did not call the retrieval tool"


@pytest.mark.parametrize("case", INVALID_CASES, ids=[c["id"] for c in INVALID_CASES])
def test_invalid_query_is_refused(agent: PDFAgent, case: dict):
    resp = agent.chat(case["question"])
    print(f"\n[{case['id']}] {case['question']}\n-> {resp.answer.encode('ascii', 'replace').decode('ascii')}\n")
    assert resp.refused is True, (
        f"Agent should have refused ({case['reason']}). Got: {resp.answer}"
    )
    assert _is_refusal(resp.answer), (
        f"Refusal lacks expected marker phrase: {resp.answer}"
    )


def test_multilingual_query(agent: PDFAgent):
    """Bonus: agent should answer correctly even when asked in another language."""
    q = "¿Cuál fue el ingreso total de la empresa en el año fiscal 2025?"
    resp = agent.chat(q)
    safe_q = q.encode("ascii", "replace").decode("ascii")
    safe_a = resp.answer.encode("ascii", "replace").decode("ascii")
    print(f"\n[multilingual-es] {safe_q}\n-> {safe_a}\n")
    assert resp.refused is False
    assert "184.6" in resp.answer
    assert _has_citation(resp.answer)
