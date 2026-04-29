"""ReadIt — strictly grounded PDF chat.

Run: ./venv/Scripts/python.exe -m streamlit run app/ui.py
"""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

import streamlit as st

from app.service import get_service


# ─────────────────────────────────────────────────────────────────────────────
# Page configuration
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ReadIt — Chat with any PDF",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────────────────────────────────────
# Custom CSS — gradients, cards, citation pills, chat polish
# ─────────────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
/* Hide only the "Made with Streamlit" footer. Keep the header and
   the three-dot menu (Rerun, Settings, Record screencast, Print, About)
   visible — the user expects native Streamlit controls to work. */
footer {visibility: hidden;}
header[data-testid="stHeader"] {
    background: transparent !important;
}
/* Sidebar collapse/expand control — make it visible above the header */
button[data-testid="stSidebarCollapseButton"],
button[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"] {
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 9999 !important;
}

/* App-wide subtle gradient backdrop */
.stApp {
    background:
        radial-gradient(circle at 0% 0%, rgba(99,102,241,0.06) 0%, transparent 35%),
        radial-gradient(circle at 100% 0%, rgba(236,72,153,0.05) 0%, transparent 40%),
        radial-gradient(circle at 50% 100%, rgba(14,165,233,0.04) 0%, transparent 40%),
        #ffffff;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
    border-right: 1px solid rgba(99,102,241,0.12);
}

/* Hero header */
.readit-hero {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
    color: white;
    padding: 28px 32px;
    border-radius: 18px;
    margin-bottom: 22px;
    box-shadow: 0 14px 40px rgba(99,102,241,0.28);
    position: relative;
    overflow: hidden;
}
.readit-hero::after {
    content: "";
    position: absolute;
    top: -40%; right: -10%;
    width: 320px; height: 320px;
    background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, transparent 70%);
    pointer-events: none;
}
.readit-hero h1 {
    margin: 0 0 6px 0;
    font-size: 2.1rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}
.readit-hero p {
    margin: 0;
    opacity: 0.92;
    font-size: 1.02rem;
}
.readit-hero .badge {
    display: inline-block;
    background: rgba(255,255,255,0.18);
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin-right: 8px;
    backdrop-filter: blur(6px);
    border: 1px solid rgba(255,255,255,0.25);
}

/* Sidebar logo */
.readit-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0 18px 0;
    border-bottom: 1px solid rgba(99,102,241,0.15);
    margin-bottom: 14px;
}
.readit-logo .logo-icon {
    width: 38px; height: 38px;
    background: linear-gradient(135deg, #6366f1 0%, #ec4899 100%);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    color: white; font-size: 20px; font-weight: 700;
    box-shadow: 0 4px 12px rgba(99,102,241,0.3);
}
.readit-logo .logo-text {
    font-weight: 800;
    font-size: 1.4rem;
    background: linear-gradient(135deg, #6366f1 0%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.readit-logo .logo-tag {
    font-size: 0.72rem;
    color: #64748b;
    font-weight: 500;
}

/* Feature cards on welcome screen */
.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 14px;
    margin: 18px 0;
}
.feature-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 18px;
    transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
}
.feature-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 10px 28px rgba(15,23,42,0.08);
    border-color: rgba(99,102,241,0.4);
}
.feature-card .icon {
    width: 40px; height: 40px;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; margin-bottom: 10px;
}
.feature-card.f1 .icon { background: rgba(99,102,241,0.12); }
.feature-card.f2 .icon { background: rgba(236,72,153,0.12); }
.feature-card.f3 .icon { background: rgba(14,165,233,0.12); }
.feature-card.f4 .icon { background: rgba(34,197,94,0.12); }
.feature-card h4 {
    margin: 0 0 6px 0;
    font-size: 1rem;
    font-weight: 700;
    color: #0f172a;
}
.feature-card p {
    margin: 0;
    font-size: 0.86rem;
    color: #475569;
    line-height: 1.45;
}

/* Doc info metric cards */
.doc-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 8px 0 14px 0;
}
.doc-stat {
    background: white;
    border: 1px solid rgba(99,102,241,0.18);
    border-radius: 10px;
    padding: 10px 12px;
}
.doc-stat .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #64748b;
    font-weight: 600;
}
.doc-stat .value {
    font-size: 1.3rem;
    font-weight: 800;
    color: #0f172a;
    margin-top: 2px;
}
.doc-name {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 10px 12px;
    font-size: 0.85rem;
    color: #334155;
    word-break: break-all;
    margin-bottom: 8px;
}
.doc-name .ico { margin-right: 6px; }

/* Citation pills inside chat answers */
.stChatMessage p code, .stMarkdown p code {
    background: rgba(99,102,241,0.10);
    color: #4338ca;
    border: 1px solid rgba(99,102,241,0.25);
    padding: 1px 7px;
    border-radius: 999px;
    font-size: 0.82em;
    font-weight: 600;
}

/* Make citation markers [p. N] stand out via JS-injected span */
.cite-pill {
    display: inline-block;
    background: linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(236,72,153,0.10) 100%);
    color: #4338ca;
    border: 1px solid rgba(99,102,241,0.28);
    padding: 1px 9px;
    border-radius: 999px;
    font-size: 0.78em;
    font-weight: 700;
    margin: 0 2px;
    vertical-align: 1px;
}

/* Refusal banner */
.refusal-tag {
    display: inline-block;
    background: rgba(245,158,11,0.12);
    color: #b45309;
    border: 1px solid rgba(245,158,11,0.35);
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    margin-bottom: 6px;
}

/* Suggested question chips */
.chip-row { margin-top: 10px; }
.stButton button[kind="secondary"] {
    border-radius: 999px !important;
    border: 1px solid rgba(99,102,241,0.28) !important;
    color: #4338ca !important;
    background: rgba(99,102,241,0.06) !important;
    font-weight: 600 !important;
    font-size: 0.84rem !important;
    transition: all 0.15s ease !important;
}
.stButton button[kind="secondary"]:hover {
    background: rgba(99,102,241,0.14) !important;
    transform: translateY(-1px) !important;
}

/* Primary buttons */
.stButton button[kind="primary"] {
    border-radius: 10px !important;
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    border: none !important;
    color: white !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 14px rgba(99,102,241,0.35) !important;
}

/* File uploader styling */
[data-testid="stFileUploader"] section {
    border: 2px dashed rgba(99,102,241,0.4) !important;
    border-radius: 14px !important;
    background: rgba(99,102,241,0.04) !important;
    padding: 18px !important;
}

/* Chat messages */
[data-testid="stChatMessage"] {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 14px !important;
    box-shadow: 0 2px 10px rgba(15,23,42,0.04) !important;
    padding: 14px 18px !important;
    margin-bottom: 10px !important;
}

/* Expander */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    font-weight: 600 !important;
    color: #475569 !important;
}

/* Footer */
.readit-footer {
    text-align: center;
    color: #94a3b8;
    font-size: 0.75rem;
    margin-top: 28px;
    padding-top: 18px;
    border-top: 1px solid #e2e8f0;
}
.readit-footer a { color: #6366f1; text-decoration: none; }

/* Sidebar caption */
.sidebar-note {
    font-size: 0.78rem;
    color: #64748b;
    line-height: 1.5;
    background: rgba(99,102,241,0.05);
    border-left: 3px solid #6366f1;
    padding: 10px 12px;
    border-radius: 6px;
    margin-top: 12px;
}
</style>
"""


SUGGESTED_QUESTIONS = [
    "Summarize this document in 5 bullet points.",
    "What are the most important numbers or statistics?",
    "List the key entities (people, places, products) mentioned.",
    "What does the document NOT cover?",
]


CITATION_RE = re.compile(r"\[p\.?\s*\d+(?:\s*[–-]\s*\d+)?\]", re.IGNORECASE)


def _render_with_pills(text: str) -> str:
    """Wrap [p. N] citations in styled pill spans for the chat bubble."""
    return CITATION_RE.sub(lambda m: f"<span class='cite-pill'>{m.group(0)}</span>", text)


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────
def _init_state() -> None:
    st.session_state.setdefault("doc_id", None)
    st.session_state.setdefault("doc_info", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("queued_prompt", None)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            """
            <div class="readit-logo">
                <div class="logo-icon">R</div>
                <div>
                    <div class="logo-text">ReadIt</div>
                    <div class="logo-tag">Chat with any PDF · grounded answers</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### 📤 Upload your document")
        uploaded = st.file_uploader(
            "Drop a PDF here",
            type=["pdf"],
            label_visibility="collapsed",
        )
        if uploaded is not None:
            file_bytes = uploaded.getvalue()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)
            with st.spinner("📚 Indexing your PDF…"):
                try:
                    info = get_service().ingest(tmp_path, uploaded.name)
                except Exception as e:
                    st.error(f"Failed to ingest PDF: {e}")
                    return
                finally:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            if (
                st.session_state.get("doc_id") != info.doc_id
                or not st.session_state.get("messages")
            ):
                st.session_state["messages"] = []
            st.session_state["doc_id"] = info.doc_id
            st.session_state["doc_info"] = info
            st.toast(f"Indexed “{info.filename}” · {info.num_pages} pages", icon="✅")

        info = st.session_state.get("doc_info")
        if info:
            st.markdown("#### 📄 Document")
            st.markdown(
                f"<div class='doc-name'><span class='ico'>📑</span>{info.filename}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class="doc-stats">
                    <div class="doc-stat">
                        <div class="label">Pages</div>
                        <div class="value">{info.num_pages}</div>
                    </div>
                    <div class="doc-stat">
                        <div class="label">Chunks</div>
                        <div class="value">{info.num_chunks}</div>
                    </div>
                </div>
                <div class="doc-stat" style="margin-bottom:10px;">
                    <div class="label">Doc ID</div>
                    <div class="value" style="font-size:0.85rem;font-family:monospace;">{info.doc_id}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            num_msgs = len(st.session_state.get("messages", []))
            num_user = sum(1 for m in st.session_state["messages"] if m["role"] == "user")
            st.markdown(
                f"""
                <div class="doc-stats">
                    <div class="doc-stat">
                        <div class="label">Questions</div>
                        <div class="value">{num_user}</div>
                    </div>
                    <div class="doc-stat">
                        <div class="label">Messages</div>
                        <div class="value">{num_msgs}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("🗑️  Clear conversation", use_container_width=True):
                st.session_state["messages"] = []
                st.rerun()

        st.markdown(
            """
            <div class="sidebar-note">
              <b>🔒 Strictly grounded.</b> ReadIt only answers from your PDF
              and cites page numbers. Off-topic questions are politely
              refused.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="readit-footer">
              Built with Streamlit · Groq Llama 3.3 · FAISS<br/>
              <span style="opacity:.7;">v1.0 — internship project</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Welcome / empty state
# ─────────────────────────────────────────────────────────────────────────────
def _render_welcome() -> None:
    st.markdown(
        """
        <div class="feature-grid">
          <div class="feature-card f1">
            <div class="icon">🎯</div>
            <h4>Strict grounding</h4>
            <p>Every answer is sourced from your PDF and cites the page.
            No hallucinations from training data.</p>
          </div>
          <div class="feature-card f2">
            <div class="icon">🔍</div>
            <h4>Hybrid retrieval</h4>
            <p>FAISS dense vectors + BM25 keyword search fused for precise,
            page-aware passages.</p>
          </div>
          <div class="feature-card f3">
            <div class="icon">🌐</div>
            <h4>Multilingual</h4>
            <p>Ask in Spanish, Hindi, French — the agent answers in your
            language with citations preserved.</p>
          </div>
          <div class="feature-card f4">
            <div class="icon">🛡️</div>
            <h4>Safe refusal</h4>
            <p>If your question isn't covered by the PDF, ReadIt politely
            declines instead of guessing.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info("👈  Upload a PDF in the sidebar to start chatting.")


def _render_suggested_chips() -> None:
    if not st.session_state.get("doc_id"):
        return
    if st.session_state.get("messages"):
        return  # Only show before first question
    st.caption("✨  Try one of these to get started:")
    cols = st.columns(len(SUGGESTED_QUESTIONS))
    for i, q in enumerate(SUGGESTED_QUESTIONS):
        with cols[i]:
            if st.button(q, key=f"suggest-{i}", type="secondary", use_container_width=True):
                st.session_state["queued_prompt"] = q
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Chat history
# ─────────────────────────────────────────────────────────────────────────────
def _render_messages() -> None:
    for msg in st.session_state["messages"]:
        avatar = "📖" if msg["role"] == "assistant" else "🧑‍💻"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant" and msg.get("refused"):
                st.markdown(
                    "<span class='refusal-tag'>⚠️ Out of scope</span>",
                    unsafe_allow_html=True,
                )
            st.markdown(_render_with_pills(msg["content"]), unsafe_allow_html=True)
            if msg["role"] == "assistant" and msg.get("retrieved"):
                with st.expander(f"🔎 Retrieved context · {len(msg['retrieved'])} passages"):
                    for r in msg["retrieved"][:6]:
                        section = f" · § {r['section']}" if r.get("section") else ""
                        st.markdown(
                            f"**📄 Page {r['page']}**  ·  score `{r.get('score', 0):.3f}`{section}"
                        )
                        snippet = r["text"][:500] + ("…" if len(r["text"]) > 500 else "")
                        st.caption(snippet)


# ─────────────────────────────────────────────────────────────────────────────
# Chat turn
# ─────────────────────────────────────────────────────────────────────────────
def _handle_prompt(prompt: str) -> None:
    st.session_state["messages"].append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)

    history = []
    for m in st.session_state["messages"][:-1]:
        if m["role"] in ("user", "assistant"):
            history.append({"role": m["role"], "content": m["content"]})

    with st.chat_message("assistant", avatar="📖"):
        with st.spinner("📖 Reading the document…"):
            try:
                resp = get_service().chat(
                    st.session_state["doc_id"],
                    prompt,
                    history=history,
                )
            except Exception as e:
                err = f"⚠️ Error: {e}"
                st.error(err)
                st.session_state["messages"].append(
                    {"role": "assistant", "content": err, "retrieved": [], "refused": True}
                )
                return

        if resp.refused:
            st.markdown(
                "<span class='refusal-tag'>⚠️ Out of scope</span>",
                unsafe_allow_html=True,
            )
        st.markdown(_render_with_pills(resp.answer), unsafe_allow_html=True)

        if resp.retrieved:
            with st.expander(f"🔎 Retrieved context · {len(resp.retrieved)} passages"):
                for r in resp.retrieved[:6]:
                    section = f" · § {r['section']}" if r.get("section") else ""
                    st.markdown(
                        f"**📄 Page {r['page']}**  ·  score `{r.get('score', 0):.3f}`{section}"
                    )
                    snippet = r["text"][:500] + ("…" if len(r["text"]) > 500 else "")
                    st.caption(snippet)

    st.session_state["messages"].append(
        {
            "role": "assistant",
            "content": resp.answer,
            "citations": resp.citations,
            "retrieved": resp.retrieved,
            "refused": resp.refused,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    _init_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    info = st.session_state.get("doc_info")
    badge = (
        f"<span class='badge'>📄 {info.filename}</span>"
        f"<span class='badge'>📑 {info.num_pages} pages</span>"
        if info
        else "<span class='badge'>⚡ Powered by Llama 3.3 70B + FAISS</span>"
    )
    st.markdown(
        f"""
        <div class="readit-hero">
            <div style="margin-bottom:10px;">{badge}</div>
            <h1>📖 ReadIt</h1>
            <p>Upload any PDF and chat with it. Strictly grounded answers, page-level citations, multilingual, and a hard refusal when something isn't in your document.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_sidebar()

    if st.session_state.get("doc_id") is None:
        _render_welcome()
        return

    _render_messages()
    _render_suggested_chips()

    queued = st.session_state.pop("queued_prompt", None)
    typed = st.chat_input("Ask anything about the document…")
    prompt = queued or typed

    if prompt:
        _handle_prompt(prompt)


if __name__ == "__main__":
    main()
