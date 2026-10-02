"""Chunk pages into semantically meaningful segments."""

from __future__ import annotations

import os
import re

from src.config import load_env

load_env()

CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", "800"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "100"))


def _split_sentences(text: str) -> list[str]:
    """Split text into paragraph/sentence-like segments."""
    # Split on newlines first (loader output is line-based), then on sentence ends
    segments: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        # further split very long lines on sentence boundaries
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if part:
                segments.append(part)
    return segments


def chunk_text(text: str, max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Paragraph/heading-aware chunking.

    Segments are merged into chunks up to ~max_chars; each new chunk
    starts with a small overlap (in characters) of the previous chunk's tail.
    """
    segments = _split_sentences(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for seg in segments:
        if current_len + len(seg) + 1 > max_chars and current:
            chunk = " ".join(current).strip()
            chunks.append(chunk)
            # start next chunk with an overlap from the tail of this one
            if overlap > 0 and chunk:
                tail = chunk[-overlap:].strip()
                # trim partial word at the start of the tail
                space = tail.find(" ")
                if 0 < space < len(tail) - 1:
                    tail = tail[space + 1 :]
                current = [tail] if tail else []
                current_len = len(tail)
            else:
                current = []
                current_len = 0
        current.append(seg)
        current_len += len(seg) + 1

    if current:
        chunks.append(" ".join(current).strip())

    return [c for c in chunks if c]


def chunk_pages(
    pages: list[dict], max_chars: int = CHUNK_MAX_CHARS, overlap: int = CHUNK_OVERLAP
) -> list[dict]:
    """Chunk every loaded page.

    Returns list of {"text", "url", "scheme", "chunk_id"}.
    """
    all_chunks: list[dict] = []
    for page in pages:
        chunks = chunk_text(page["text"], max_chars=max_chars, overlap=overlap)
        for idx, chunk in enumerate(chunks):
            all_chunks.append(
                {
                    "text": chunk,
                    "url": page["url"],
                    "scheme": page["scheme"],
                    "chunk_id": idx,
                }
            )
        avg = sum(len(c) for c in chunks) / max(len(chunks), 1)
        print(f"{page['scheme']}: {len(chunks)} chunks, avg {avg:.0f} chars")
    return all_chunks


if __name__ == "__main__":
    from src.ingestion.loader import CORPUS, load_all

    pages = load_all(CORPUS)
    chunks = chunk_pages(pages)
    print(f"\nTotal chunks: {len(chunks)}")
    for c in chunks[:2]:
        print("----", c["scheme"], "chunk", c["chunk_id"], "----")
        print(c["text"][:300], "\n")
