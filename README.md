# 📖 ReadIt — PDF-Constrained Conversational Agent

## 🔗 Quick Links

- 🚀 **Deployed Application:** [Open the live app](https://readit-8n9hjsoiczfjqjiuwbcdtw.streamlit.app/)
- 🎬 **Live Demo Video:** [Watch the walkthrough](https://your-demo-video-url)
- 📊 **Presentation PPT:** [View the PPT Slides](https://your-ppt-drive-link)

A polished chat agent that answers questions about a single PDF and **only**
that PDF. Every factual claim is grounded with a page citation; out-of-scope
questions are explicitly refused.

---

## ✨ Highlights

- **Strict grounding** — agent calls a `retrieve_from_pdf` tool before
  answering; never uses prior knowledge.
- **Hybrid retrieval** — FAISS dense vectors + BM25 sparse keyword search,
  fused with reciprocal rank fusion.
- **Citation enforcement** — responses missing `[p. N]` citations are
  re-prompted; if the model still cannot cite, it is forced to refuse.
- **Confidence-gated refusal** — when retrieval scores are weak, the tool
  output explicitly tells the model the document does not contain the
  answer.
- **Multilingual** — works in any language Llama 3.3 supports (Spanish,
  Hindi, French, etc.); citations stay in `[p. N]` format.
- **Two interfaces** — Streamlit chat UI and FastAPI REST endpoint, both
  backed by the same service layer.
- **Automated evaluation harness** — pytest suite with the 5 valid + 3
  invalid queries required by the brief, plus a multilingual case.

---

## 🏗️ System Architecture

```
                ┌──────────────────────────┐
                │  User: "What was the     │
                │   FY2025 uptime?"        │
                └────────────┬─────────────┘
                             │
        ┌────────────────────┴────────────────────┐
        ▼                                         ▼
┌──────────────────┐                  ┌──────────────────────┐
│   Streamlit UI   │                  │   FastAPI REST API   │
│   (app/ui.py)    │                  │   (app/api.py)       │
└────────┬─────────┘                  └──────────┬───────────┘
         │                                       │
         └────────────────┬──────────────────────┘
                          ▼
              ┌────────────────────────┐
              │     PDF Service        │
              │   (app/service.py)     │  ← single source of truth
              └────────────┬───────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐    ┌──────────────┐   ┌──────────────────┐
│  Ingestion   │    │  Hybrid      │   │  Agent Loop      │
│  ingest.py   │    │  Retriever   │   │  agent.py        │
│              │    │              │   │                  │
│  PyMuPDF +   │    │  FAISS +     │   │  Groq (Llama     │
│  pypdf       │    │  BM25 + RRF  │   │  3.3 70B) with   │
│  → page      │    │  retriever.py│   │  tool calling    │
│    chunks    │    │              │   │                  │
└──────┬───────┘    └──────┬───────┘   └────────┬─────────┘
       │                   │                    │
       │                   ▼                    │
       │           ┌──────────────┐             │
       └──────────▶│  Persistent  │             │
                   │  index dir   │◀────────────┘
                   │  data/index/ │   retrieve_from_pdf()
                   └──────────────┘   tool call
                           ▲
                           │  ground answer
                           ▼
              ┌────────────────────────┐
              │  Citation Enforcement  │
              │  • check [p. N]        │
              │  • re-prompt if absent │
              │  • refuse if unsourced │
              └────────────┬───────────┘
                           ▼
              ┌────────────────────────┐
              │  Response with         │
              │  citations + retrieved │
              │  context for audit     │
              └────────────────────────┘
```

**Key idea:** the model is *forced through* a retrieval tool call before it
can answer. Tool output is the only context it sees. A post-hoc citation
check guarantees that if the model deviates, we either re-ground or refuse.

---

## 🧰 Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| **LLM** | Groq Llama 3.3 70B | Fast (~400 tok/s), free tier, OpenAI-compatible tool calling |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` | 384-dim, ~80 MB, runs locally, no extra API key |
| **Vector store** | FAISS (`IndexFlatIP`) | Zero infra, exact cosine search, cheap to rebuild |
| **Sparse search** | `rank_bm25` (BM25Okapi) | Catches rare keywords dense embeddings miss |
| **Fusion** | Reciprocal Rank Fusion (k=60) | Tuning-free combiner — robust across PDFs |
| **PDF parsing** | PyMuPDF (`fitz`) → `pypdf` fallback | Better table/column handling, with a safety net |
| **Web UI** | Streamlit 1.57 | Fast to ship a polished chat UI; native dark/light theming |
| **API** | FastAPI + Uvicorn | Auto-Swagger; identical service layer to the UI |
| **Tests** | pytest | One harness for offline + live; parametrised valid/invalid cases |
| **Config** | `python-dotenv` | `.env`-driven settings, no hard-coded keys |
| **Deploy** | Streamlit Community Cloud | Zero-config from GitHub; secrets UI for `GROQ_API_KEY` |

---

## 🔄 How It Works

### Ingestion (one-time per upload)

1. **Parse** the PDF page by page with PyMuPDF (PyPDF as fallback). Each
   page's raw text is collected with its page number intact.
2. **Normalise** the text — strip soft-hyphens, de-hyphenate line breaks,
   collapse whitespace.
3. **Chunk** with a word-based sliding window (default 900 words, 150
   overlap) **per page**. Page-bounded chunks guarantee that every
   citation maps to a contiguous region.
4. **Embed** each chunk with sentence-transformers (`all-MiniLM-L6-v2`,
   normalised), and add to a FAISS `IndexFlatIP`.
5. **Build** a parallel BM25 index for sparse keyword retrieval.
6. **Persist** chunks + embeddings + FAISS index + BM25 to
   `data/index/<sha256-prefix>/`. Re-uploading the same PDF skips
   re-indexing.

### Query (every chat turn)

1. The user types a question. The Streamlit UI / FastAPI passes it to
   `PDFService.chat(question, history)`.
2. The agent sends `[system, history, user]` to Groq with the
   `retrieve_from_pdf` tool exposed.
3. The model issues one (or more) tool calls. For each:
   - The retriever runs **dense + sparse + RRF** and returns the top
     `top_k` passages with their pages, sections, and scores.
   - If every passage scores below the **refusal threshold**
     (default 0.25), the tool result includes a hint telling the model
     the document likely doesn't contain the answer.
4. The model produces a natural-language answer that **must** end with
   `[p. N]` citations.
5. **Citation enforcement**: if the answer has no citation and isn't a
   refusal, we send one corrective re-prompt asking the model to either
   cite or refuse. If it still fails, we hard-refuse.
6. The final response is returned with the answer text, parsed
   citations, retrieved context, and a `refused` flag — both UIs render
   them.

---

## 📁 Folder Structure

```
stair/                          # repo root
├── .devcontainer/              # GitHub Codespaces config (1-click dev env)
│   └── devcontainer.json
├── .streamlit/                 # Streamlit theme + server settings
│   └── config.toml
├── app/                        # application code
│   ├── __init__.py
│   ├── config.py               # env-driven settings (Groq key, top-k, etc.)
│   ├── ingest.py               # PDF → page-aware chunks
│   ├── retriever.py            # FAISS + BM25 + Reciprocal Rank Fusion
│   ├── prompts.py              # strict grounding system prompt
│   ├── agent.py                # tool-calling loop + citation enforcement
│   ├── service.py              # singleton orchestrator (ingest + chat)
│   ├── api.py                  # FastAPI surface (/upload, /chat, /health)
│   ├── ui.py                   # Streamlit chat UI (light + dark themes)
│   └── static/
│       └── readit-logo.png     # brand logo (favicon, sidebar, hero)
├── Scripts/
│   └── generate_sample_pdf.py  # builds tests/fixtures/sample.pdf
├── tests/                      # pytest suite (offline + live)
│   ├── __init__.py
│   ├── test_retriever.py       # 5 offline tests, no API key
│   ├── test_agent.py           # 5 valid + 3 invalid + multilingual (live)
│   └── fixtures/
│       └── sample.pdf          # 6-page fictional ACME report
├── data/                       # ignored — runtime PDFs + indexes
│   ├── uploads/                # uploaded PDFs (sha256-named)
│   └── index/                  # per-doc FAISS + BM25 + embeddings
├── .env.example                # template — copy to .env, add your key
├── .gitignore
├── requirements.txt
├── README.md                   # this file
└── TECHNICAL_NOTE.md           # design decisions & trade-offs
```

---

## 🛠️ Setup

### 1. Get a Groq API key

1. Go to <https://console.groq.com>, sign up.
2. Create an API key in **API Keys → Create API Key**.
3. Free tier is generous (Llama 3.3 70B at 30 req/min).

### 2. Install

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements.txt   # Windows
# source venv/bin/activate; pip install -r requirements.txt   # Linux/Mac
```

### 3. Configure

```bash
cp .env.example .env
# Open .env and paste your GROQ_API_KEY
```

### 4. Generate the sample PDF (already committed; only needed if you change it)

```bash
./venv/Scripts/python Scripts/generate_sample_pdf.py
```

---

## ▶️ Run

### Streamlit UI (recommended for graders)

```bash
./venv/Scripts/python -m streamlit run app/ui.py
```

Open <http://localhost:8501>. Upload a PDF in the sidebar and chat.

### FastAPI REST

```bash
./venv/Scripts/python -m uvicorn app.api:app --reload --port 8000
```

Open <http://localhost:8000/docs> for interactive Swagger.

Quick test:

```bash
curl -F "file=@tests/fixtures/sample.pdf" http://localhost:8000/upload
# → {"doc_id": "...", "filename": "sample.pdf", "num_pages": 6, ...}

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"doc_id": "<id from upload>", "question": "What was the average uptime?"}'
```

---

## ✅ Test

### Offline (no API key needed)

```bash
./venv/Scripts/python -m pytest tests/test_retriever.py -v
```

Verifies ingestion, chunking, hybrid retrieval, and the out-of-scope score
threshold.

### End-to-end (requires GROQ_API_KEY)

```bash
./venv/Scripts/python -m pytest tests/test_agent.py -v -s
```

Runs the **5 valid + 3 invalid** queries from the brief plus a Spanish
multilingual query.

---

## 📑 Sample PDF — `tests/fixtures/sample.pdf`

A 6-page fictional ACME Robotics field-performance report. Picked because:

- The numbers are specific and unique (e.g. *97.2% uptime*, *USD 184.6 M
  revenue*) so hallucination is easy to detect.
- It has structured sections, financials, and statistics across pages.
- It is fictional, so we know the model has no prior knowledge of it.

You can use it for your own demos, or upload any other PDF.

### 5 valid queries (and what good answers look like)

| # | Query | Expected page | Must mention |
|---|-------|---------------|--------------|
| 1 | What was the average uptime of the R-7 in FY2025? | 1 | `97.2%` |
| 2 | What is the most common failure mode and how many incidents did it cause? | 1, 4 | `wheel-encoder drift`, `233`, `38%` |
| 3 | What is the payload capacity of the R-7? | 2 | `250 kg` |
| 4 | Which is the largest single deployment and how many units does it have? | 3 | `Memphis`, `312` |
| 5 | What was the total revenue in FY2025 and the gross margin on hardware? | 5 | `184.6 million`, `34.2%` |

Every answer must end relevant sentences with `[p. N]` citations.

### 3 invalid / out-of-scope queries (must be refused)

| # | Query | Why it must be refused |
|---|-------|------------------------|
| 1 | What is the capital of France? | General knowledge, unrelated. |
| 2 | Write me a short poem about robots. | Creative request, outside document scope. |
| 3 | What is the R-7's network protocol stack and exact TCP port assignments? | Topic-adjacent but the document does not cover this. The agent must say *"I couldn't find that in the document."* rather than guess. |

### Bonus: multilingual

```
¿Cuál fue el ingreso total de la empresa en el año fiscal 2025?
```

Expected: a Spanish-language answer that includes `184.6` and a `[p. 5]`
citation.

---

## 🔍 How to verify the agent is *actually* grounded

1. **Remove a page from the PDF and re-upload it** — the agent should now
   refuse questions about that page.
2. **Ask a topic-adjacent but unsupported question** (#3 in invalid set
   above) — the agent should refuse rather than improvise.
3. **Inspect the "Retrieved context (debug)" expander in the Streamlit UI**
   — every cited page must appear in the retrieved excerpts.
4. **Check the `tool_calls` field in the FastAPI `/chat` response** —
   should be ≥ 1 for any factual answer.

---

## ⚠️ Limitations

Honest list of what this build does *not* do well:

- **Single document per session.** No multi-PDF retrieval, no document
  picker. The service maps `doc_id → retriever`; you'd need to expose a
  picker in the UI to handle a corpus.
- **No table extraction.** PyMuPDF's `get_text("text")` flattens tables
  into prose. PDFs that put critical numbers in tables (financial
  statements, datasheets) lose structure on ingest. `pdfplumber` would be
  the right addition.
- **Page-bounded chunks.** Sentences that wrap across page breaks may be
  split. The trade-off is that every citation is guaranteed to be a
  contiguous region.
- **Word-based sliding window** (not semantic). Fast and deterministic,
  but a paragraph that's tightly cohesive may get cut mid-thought. A
  sentence-aware splitter (e.g. NLTK) would help marginally.
- **No reranker.** Top-k from RRF is sent straight to the model. A
  cross-encoder reranker (e.g. `bge-reranker-base`) would improve top-1
  precision on dense technical PDFs by a few points, at the cost of
  another model load.
- **No verification pass.** A second LLM call to verify each cited
  passage against the original chunk would catch a class of subtle
  hallucinations (paraphrase drift). The corrective-citation re-prompt
  catches most of the value at half the cost.
- **Refusal threshold is global.** The 0.25 cosine threshold works for
  the sample PDF but isn't calibrated per-document; a corpus with a
  different vocabulary could need a different value.
- **No conversation summarisation.** Long chat histories are passed
  verbatim to the model. After ~20 turns you'll see latency and token
  cost rise.
- **Streamlit Cloud RAM cap (1 GB).** Sentence-transformers + FAISS is
  ~120 MB resident — fine for hundreds of pages, but a 500-page PDF with
  fine-grained chunking could hit ceilings.

---

## 🚀 Future Improvements

If this were going to production, these would be the next ten things to
ship, roughly in priority order:

1. **Cross-encoder reranking** of the top-20 RRF results. Largest
   precision win; ~1 sec extra per query.
2. **`pdfplumber` table extraction** for documents where numbers live
   inside tables.
3. **Verification pass** — a second cheap LLM call that scores each cited
   claim against its source chunk; reject if any claim is below
   threshold.
4. **Multi-document support** — corpus picker in the UI, multi-doc
   retrieval, doc-aware citations (e.g. `[Doc A, p. 3]`).
5. **Per-document threshold calibration** — auto-calibrate the refusal
   cosine threshold per upload using a held-out distribution of
   in-scope vs out-of-scope queries.
6. **Streaming responses** in the Streamlit UI (Groq supports SSE).
7. **Conversation summarisation** — collapse old turns into a compact
   summary once history exceeds N tokens.
8. **OCR fallback** for scanned PDFs (Tesseract or Apple's Vision).
9. **User accounts + workspace persistence** so re-uploads aren't needed
   between sessions.
10. **Observability**: structured logs (request ID, query, top-k scores,
    refusal reason) → a dashboard for tracking refusal rate, average
    citation count, and average tool calls per turn.

---

## 🧯 Troubleshooting

- **`ImportError: faiss`** — re-run `pip install -r requirements.txt` inside
  the venv. On some Windows setups install `faiss-cpu` from a wheel.
- **`GROQ_API_KEY is not set`** — copy `.env.example` to `.env` and paste
  your key.
- **Embedding model download is slow on first run** — `all-MiniLM-L6-v2`
  is ~80 MB and is cached locally after the first ingest.
- **Streamlit caches a stale doc** — click "Clear conversation" or restart
  the app.
- **`ModuleNotFoundError: No module named 'app'` on Streamlit Cloud** —
  fixed in `app/ui.py` (project root injected into `sys.path`); pull
  latest if you forked from before this fix.

---

