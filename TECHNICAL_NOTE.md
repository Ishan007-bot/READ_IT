# Technical Note — PDF-Constrained Conversational Agent

## 1. Goal & non-goals

**Goal.** Build an agent that reliably answers questions about a single
PDF, with strict grounding, page-level citations, and explicit refusal of
out-of-scope questions.

**Non-goals.** Multi-document corpora, user accounts, long-term memory
across sessions, ranking optimisation beyond a sensible default. These
were deliberately deferred to keep the surface area small.

## 2. Architecture

```
        ┌──────────────┐         ┌──────────────────────────────┐
        │ Streamlit UI │         │ FastAPI (/upload, /chat)     │
        └──────┬───────┘         └──────────────┬───────────────┘
               │                                │
               └────────────┬───────────────────┘
                            ▼
                ┌──────────────────────┐
                │   PDFService         │
                │  (singleton, in-mem) │
                └─────────┬────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
   ┌──────────┐    ┌──────────────┐   ┌──────────────┐
   │ ingest.py│    │ retriever.py │   │  agent.py    │
   │  PDF →   │    │  FAISS +     │   │  Groq Llama  │
   │  chunks  │    │  BM25 + RRF  │   │  + tool loop │
   └──────────┘    └──────────────┘   └──────┬───────┘
                                             │
                                      ┌──────▼───────┐
                                      │  Citation    │
                                      │  enforcement │
                                      └──────────────┘
```

Both UIs go through the **same** `PDFService`, so the FastAPI tests and
Streamlit demo behave identically.

## 3. Pipeline stages

### 3.1 Ingestion (`app/ingest.py`)

- Primary parser: **PyMuPDF (fitz)** — handles columns, ligatures,
  embedded text well.
- Fallback: **pypdf** — pure-Python, deals with PDFs PyMuPDF rejects.
- Page numbers are tracked on the `Chunk` so they survive into the agent
  output as citations.
- A regex heuristic (`^N(.N)*\s+Capitalised…`) detects section headings
  and attaches them to chunks, which both helps retrieval and gives a
  nicer UI display.
- Chunking is **word-based sliding window**, default 900 words / 150
  overlap, *per page*. We chose page-bounded chunks (rather than
  cross-page) so a citation always corresponds to a real, contiguous
  region.

### 3.2 Retrieval (`app/retriever.py`)

- **Dense:** `sentence-transformers/all-MiniLM-L6-v2`, 384-dim, normalised
  embeddings + FAISS `IndexFlatIP` (cosine via inner product).
- **Sparse:** `rank_bm25.BM25Okapi` over lower-cased word-tokens.
- **Fusion:** Reciprocal Rank Fusion (k=60). RRF is robust without
  per-query tuning, which matters when we don't know what corpus the
  evaluator will upload.
- We persist `embeddings.npy`, `faiss.index`, `bm25.pkl`, and a JSON of
  the chunks under `data/index/<sha256-prefix>/`. Re-uploading the same
  PDF skips re-indexing.

**Why hybrid?** Pure dense retrieval misses queries that hinge on rare
specific tokens (`R-7`, `97.2%`, named entities). Pure sparse misses
paraphrases (`uptime` vs `availability`). RRF gets both.

### 3.3 Agent loop (`app/agent.py`)

Groq's chat API supports OpenAI-compatible tool calling. We expose one
tool, `retrieve_from_pdf(query, top_k)`, and instruct the model in the
system prompt that it MUST call this tool before answering any factual
question.

The loop:

1. Send `[system, …history, user]` with `tools=[retrieve_from_pdf]`.
2. If the model returns tool calls → execute them, append the results
   as `tool` messages, loop (max 4 iterations).
3. Otherwise it returned an answer → run citation enforcement, return.

**Why a tool, not a single-shot prompt?** Two reasons:
- It maps cleanly to the rubric's "Tool usage / Workflow design" criteria.
- It lets the model issue *multiple* retrievals when a question has
  multiple parts — e.g. "compare uptime and revenue" naturally splits
  into two queries.

### 3.4 Confidence-gated refusal

Inside `_format_tool_result`, if every retrieved chunk's cosine score is
below `RETRIEVAL_THRESHOLD` (default 0.25), we append:

> `note: All retrieval scores are weak (top score=0.11 < 0.25). The
> document likely does NOT contain the answer. Prefer to respond:
> "I couldn't find that in the document."`

This signal is the single most important lever for refusal quality. The
threshold of 0.25 was picked empirically against the sample PDF
(in-scope queries score 0.30–0.65; out-of-scope queries score < 0.15).

### 3.5 Citation enforcement

After the model answers, we check for `[p. N]` markers using a regex.
If a non-refusal response is missing citations, we send one corrective
re-prompt asking the model to either cite or refuse. If it still fails,
we downgrade to a hard refusal — better to refuse than to hallucinate.

## 4. Key design decisions

| Decision | Why |
|----------|-----|
| Local embeddings (sentence-transformers) over OpenAI | Avoids a second API key + cost; quality is fine for this scale. |
| FAISS in-memory + on-disk persist | Zero infra; rebuild is cheap (~seconds). |
| Page-bounded chunks (no cross-page) | Guarantees a citation is always a contiguous region. Slightly worse for sentences split across pages, but easier to evaluate. |
| Word-sliding window over semantic chunking | Faster, deterministic, and good enough; semantic chunking can be added later. |
| Tool-calling agent over single-shot RAG | Maps to rubric's agent-design criteria and naturally supports multi-step queries. |
| Conversation history passed verbatim | Simple "memory"; per-turn re-grounding via the retrieval tool keeps the agent honest. |
| Citation regex enforced post-hoc | Cheap insurance against the model dropping citations even when the prompt says it shouldn't. |
| Streamlit + FastAPI from one service | Two interfaces, one source of truth. Reduces test surface. |

## 5. Trade-offs we accepted

- **No re-ranking model.** A cross-encoder reranker (e.g.
  `bge-reranker-base`) would improve top-1 accuracy by a few points, but
  doubles ingestion-time deps and adds latency. RRF is a strong baseline.
- **No table-aware extraction.** PyMuPDF's `get_text("text")` flattens
  tables. For heavily tabular PDFs we'd want `pdfplumber` table
  extraction; out of scope for this assignment.
- **No verification pass.** A second LLM call to verify each cited claim
  against the cited chunk would catch a class of subtle hallucinations.
  The corrective-citation re-prompt covers most of the value at half the
  cost.
- **Single-document scope per session.** Multi-PDF support would need a
  document picker in the UI and multi-doc retrieval; doable but not
  required.

## 6. Observability

- Each `/chat` response includes:
  - `answer` — the model's response
  - `citations` — list of `[p. N]` markers found in the answer
  - `retrieved` — full retrieved passages with scores (for debugging)
  - `tool_calls` — how many times the agent invoked the retrieval tool
  - `refused` — boolean flag for downstream consumers
- The Streamlit UI exposes the same payload via a "Retrieved context
  (debug)" expander on each assistant message.
- The pytest harness prints every `(question, answer)` pair when run
  with `-s`, making evaluation runs auditable.

## 7. Performance & cost

- Indexing a 50-page PDF: ~5–10 seconds (one-time, cached).
- A typical chat turn: 1.5–3 seconds (Groq is the fastest hosted
  inference; Llama 3.3 70B at ~400 tok/s).
- Cost: free under Groq's developer tier (well within rate limits for
  evaluation).

## 8. What I'd build next

1. **Cross-encoder reranking** for the top-20 RRF results — would
   noticeably improve answer precision on technical PDFs.
2. **Table extraction** with `pdfplumber` for documents where numbers
   live in tables.
3. **Verification pass** — a second LLM call that scores each claim
   against its cited chunk; reject the response if any claim is below
   threshold.
4. **Cached embeddings of common queries** — most evaluators ask similar
   questions; a tiny cache would cut latency for demo runs.
5. **Per-document refusal-threshold calibration** — the 0.25 default works
   for the sample PDF but should be calibrated per upload using a
   held-out distribution of in-scope vs out-of-scope queries.

## 9. Mapping to the rubric

| Rubric area | Where it shows up |
|-------------|-------------------|
| Claude/LLM API | Groq (OpenAI-compatible) — `app/agent.py` |
| Vector DBs | FAISS — `app/retriever.py` |
| Retrieval design | Hybrid + RRF + page-aware chunking |
| RAG evaluation | `tests/test_retriever.py`, `tests/test_agent.py` |
| Tool usage | `retrieve_from_pdf` tool, multi-step loop |
| Memory | Conversation history threaded through every turn |
| Workflow design | Service layer orchestrating ingest → retrieve → answer → enforce |
| Hosting | Streamlit (UI) + FastAPI (API) over the same service |
| Prompt design | `app/prompts.py` — strict, with refusal examples |
| Prompting evaluation | Test suite asserts citations + refusal phrasing |
| Multilingual | `test_multilingual_query` in `tests/test_agent.py` |
