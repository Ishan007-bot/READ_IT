"""Agent loop: Groq Llama 3.3 with tool use over the hybrid retriever.

Design notes
------------
* We use Groq's OpenAI-compatible tool-calling. The model decides when to call
  `retrieve_from_pdf`. We loop until it stops calling tools or hits MAX_STEPS.
* We pass conversation history through every turn so follow-up questions
  ("what about chapter 3?") have context.
* If the retrieved chunks all score below `RETRIEVAL_THRESHOLD`, we tag the
  tool result so the model knows the document is unlikely to contain the
  answer — this is a major lever for refusal quality.
* If a non-refusal response comes back without any `[p. N]` citation, we
  do one corrective re-prompt asking the model to add citations or refuse.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List

from groq import Groq

from app.config import Settings
from app.prompts import SYSTEM_PROMPT, build_user_prompt
from app.retriever import HybridRetriever, RetrievedChunk


MAX_STEPS = 4
CITATION_RE = re.compile(r"\[p\.?\s*\d+(?:\s*[–-]\s*\d+)?\]", re.IGNORECASE)
REFUSAL_MARKERS = (
    "outside the scope",
    "couldn't find that",
    "could not find that",
    "i couldn't find",
    "i could not find",
)


TOOL_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_from_pdf",
            "description": (
                "Retrieve the most relevant excerpts from the uploaded PDF for "
                "a natural-language query. Always call this before answering "
                "any factual question about the PDF. Returns a JSON list of "
                "passages with page numbers and confidence scores. The system "
                "controls how many passages are returned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A focused search query in the same language as "
                            "the user's question. Reformulate broad questions "
                            "into specific keyword-rich queries."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    }
]


@dataclass
class AgentResponse:
    answer: str
    citations: List[dict]
    retrieved: List[dict]
    tool_calls: int
    refused: bool


def _format_tool_result(retrieved: List[RetrievedChunk], threshold: float) -> str:
    if not retrieved:
        return json.dumps(
            {
                "passages": [],
                "note": (
                    "No passages found. The document does not appear to "
                    "contain information related to this query."
                ),
            }
        )

    top_score = max(r.score for r in retrieved)
    weak = top_score < threshold

    payload = {
        "passages": [
            {
                "page": r.chunk.page,
                "section": r.chunk.section,
                "score": round(r.score, 3),
                "text": r.chunk.text,
            }
            for r in retrieved
        ],
    }
    if weak:
        payload["note"] = (
            f"All retrieval scores are weak (top score={top_score:.2f} < "
            f"{threshold:.2f}). The document likely does NOT contain the "
            "answer. Prefer to respond: \"I couldn't find that in the "
            "document.\""
        )
    return json.dumps(payload, ensure_ascii=False)


class PDFAgent:
    def __init__(self, retriever: HybridRetriever, settings: Settings):
        self.retriever = retriever
        self.settings = settings
        self.client = Groq(api_key=settings.groq_api_key)

    def _dispatch_tool(self, name: str, args: dict) -> tuple[str, List[RetrievedChunk]]:
        if name == "retrieve_from_pdf":
            query = (args.get("query") or "").strip()
            # Tolerate models that fabricate extra args (e.g. top_k as string)
            try:
                requested_k = int(args.get("top_k", self.settings.top_k))
            except (TypeError, ValueError):
                requested_k = self.settings.top_k
            top_k = max(1, min(10, requested_k))
            retrieved = self.retriever.search(query, top_k=top_k)
            return _format_tool_result(retrieved, self.settings.retrieval_threshold), retrieved
        return json.dumps({"error": f"Unknown tool: {name}"}), []

    def chat(
        self, question: str, history: List[dict] | None = None
    ) -> AgentResponse:
        history = history or []
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": build_user_prompt(question)})

        retrieved_all: List[RetrievedChunk] = []
        tool_calls = 0

        for _ in range(MAX_STEPS):
            resp = self.client.chat.completions.create(
                model=self.settings.groq_model,
                messages=messages,
                tools=TOOL_SCHEMA,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=self.settings.max_tokens,
            )
            msg = resp.choices[0].message

            if msg.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tc in msg.tool_calls:
                    tool_calls += 1
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result_str, retrieved = self._dispatch_tool(
                        tc.function.name, args
                    )
                    retrieved_all.extend(retrieved)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tc.function.name,
                            "content": result_str,
                        }
                    )
                continue

            answer = (msg.content or "").strip()
            answer, refused = self._enforce_citations(answer, messages)
            citations = self._extract_citations(answer)
            return AgentResponse(
                answer=answer,
                citations=citations,
                retrieved=[r.to_dict() for r in retrieved_all],
                tool_calls=tool_calls,
                refused=refused,
            )

        # Fallback if model loops on tool calls
        return AgentResponse(
            answer=(
                "I couldn't produce a grounded answer for that question. "
                "Please rephrase or ask something else about the document."
            ),
            citations=[],
            retrieved=[r.to_dict() for r in retrieved_all],
            tool_calls=tool_calls,
            refused=True,
        )

    # ---- post-processing --------------------------------------------------
    def _is_refusal(self, text: str) -> bool:
        low = text.lower()
        return any(m in low for m in REFUSAL_MARKERS)

    def _extract_citations(self, text: str) -> List[dict]:
        out: List[dict] = []
        for m in CITATION_RE.finditer(text):
            out.append({"marker": m.group(0)})
        return out

    def _enforce_citations(
        self, answer: str, messages: List[dict]
    ) -> tuple[str, bool]:
        """If the answer claims facts but has no citations, ask once for a
        corrected version. If still missing, downgrade to a refusal."""
        if not answer:
            return (
                "I couldn't find that in the document.",
                True,
            )
        if self._is_refusal(answer):
            return answer, True
        if CITATION_RE.search(answer):
            return answer, False

        # Corrective re-prompt
        messages_copy = list(messages)
        messages_copy.append({"role": "assistant", "content": answer})
        messages_copy.append(
            {
                "role": "user",
                "content": (
                    "Your previous answer is missing the required `[p. N]` "
                    "citations. Re-write it grounding every claim with a "
                    "page citation from the retrieved passages, OR say "
                    "\"I couldn't find that in the document.\" if the "
                    "passages don't support it."
                ),
            }
        )
        resp = self.client.chat.completions.create(
            model=self.settings.groq_model,
            messages=messages_copy,
            temperature=0.0,
            max_tokens=self.settings.max_tokens,
        )
        fixed = (resp.choices[0].message.content or "").strip()
        if fixed and (CITATION_RE.search(fixed) or self._is_refusal(fixed)):
            return fixed, self._is_refusal(fixed)

        return (
            "I couldn't find that in the document.",
            True,
        )
