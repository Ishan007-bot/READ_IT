# 📖 ReadIt — PDF-Constrained Conversational Agent

## 🔗 Quick Links

- 🚀 **Deployed Application:** [Open the live app](https://readit-8n9hjsoiczfjqjiuwbcdtw.streamlit.app/)
- 🎬 **Live Demo Video:** [Watch the walkthrough](https://your-demo-video-url)
- 📊 **Presentation PPT:** [View the PPT Slides](https://your-ppt-drive-link)

A polished chat agent that answers questions about a single PDF and **only**
that PDF. Every factual claim is grounded with a page citation; out-of-scope
questions are explicitly refused.

Built for the internship Task 3 brief.

---

## Highlights

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

## Setup

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
./venv/Scripts/python scripts/generate_sample_pdf.py
```

---

## Run

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

## Test

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

## Sample PDF — `tests/fixtures/sample.pdf`

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

## How to verify the agent is *actually* grounded

1. **Remove a page from the PDF and re-upload it** — the agent should now
   refuse questions about that page.
2. **Ask a topic-adjacent but unsupported question** (#3 in invalid set
   above) — the agent should refuse rather than improvise.
3. **Inspect the "Retrieved context (debug)" expander in the Streamlit UI**
   — every cited page must appear in the retrieved excerpts.
4. **Check the `tool_calls` field in the FastAPI `/chat` response** —
   should be ≥ 1 for any factual answer.

---

## Project layout

```
stair/
├── app/
│   ├── config.py        # env-driven settings
│   ├── ingest.py        # PDF → page-aware chunks
│   ├── retriever.py     # FAISS + BM25 + RRF
│   ├── prompts.py       # strict grounding system prompt
│   ├── agent.py         # tool-calling agent loop + citation enforcement
│   ├── service.py       # ingest + chat orchestration
│   ├── api.py           # FastAPI surface
│   └── ui.py            # Streamlit chat UI
├── scripts/
│   └── generate_sample_pdf.py
├── tests/
│   ├── test_retriever.py    # offline tests, no API key
│   ├── test_agent.py        # end-to-end, needs GROQ_API_KEY
│   └── fixtures/sample.pdf
├── data/                # ignored: uploaded PDFs + persisted indexes
├── requirements.txt
├── .env.example
├── README.md            # this file
└── TECHNICAL_NOTE.md    # architecture & design decisions
```

---

## Troubleshooting

- **`ImportError: faiss`** — re-run `pip install -r requirements.txt` inside
  the venv. On some Windows setups install `faiss-cpu` from a wheel.
- **`GROQ_API_KEY is not set`** — copy `.env.example` to `.env` and paste
  your key.
- **Embedding model download is slow on first run** — `all-MiniLM-L6-v2`
  is ~80 MB and is cached locally after the first ingest.
- **Streamlit caches a stale doc** — click "Clear conversation" or restart
  the app.

---

## License

MIT, for evaluation purposes.
