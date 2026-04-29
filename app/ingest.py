"""PDF ingestion: parse text page-by-page and chunk with metadata.

Uses PyMuPDF (fitz) when available for higher-fidelity extraction
(handles columns, tables, ligatures better) and falls back to pypdf.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class Chunk:
    chunk_id: int
    page: int
    text: str
    section: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _extract_with_fitz(pdf_path: Path) -> List[tuple[int, str]]:
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    pages: List[tuple[int, str]] = []
    try:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text))
    finally:
        doc.close()
    return pages


def _extract_with_pypdf(pdf_path: Path) -> List[tuple[int, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    pages: List[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append((i, text))
    return pages


def extract_pages(pdf_path: Path) -> List[tuple[int, str]]:
    """Return [(page_number, text), ...] using the best parser available."""
    try:
        return _extract_with_fitz(pdf_path)
    except Exception:
        return _extract_with_pypdf(pdf_path)


_HEADING_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)*\s+[A-Z][^\n]{2,80})\s*$")


def _detect_section(line: str, current: str | None) -> str | None:
    m = _HEADING_RE.match(line)
    if m:
        return m.group(1).strip()
    return current


def _normalise(text: str) -> str:
    text = text.replace("­", "")  # soft hyphen
    text = re.sub(r"-\n(?=\w)", "", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pages(
    pages: List[tuple[int, str]],
    chunk_size: int = 900,
    overlap: int = 150,
) -> List[Chunk]:
    """Word-based sliding window per page; preserves section context."""
    chunks: List[Chunk] = []
    chunk_id = 0
    current_section: str | None = None

    for page_num, raw in pages:
        text = _normalise(raw)
        if not text:
            continue

        for line in text.splitlines():
            current_section = _detect_section(line, current_section)

        words = text.split()
        if not words:
            continue

        step = max(1, chunk_size - overlap)
        for start in range(0, len(words), step):
            window = words[start : start + chunk_size]
            if not window:
                break
            chunk_text = " ".join(window).strip()
            if len(chunk_text) < 40:
                continue
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    page=page_num,
                    text=chunk_text,
                    section=current_section,
                )
            )
            chunk_id += 1
            if start + chunk_size >= len(words):
                break

    return chunks


def ingest_pdf(pdf_path: Path) -> List[Chunk]:
    pages = extract_pages(pdf_path)
    return chunk_pages(pages)
