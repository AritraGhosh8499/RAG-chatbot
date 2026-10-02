"""LLM answer generation with a grounded, facts-only prompt."""

from __future__ import annotations

import os
import re
import sys
from datetime import date

from dotenv import load_dotenv

from src.config import load_env
from src.retrieval.prompts import SYSTEM_PROMPT, build_user_prompt

load_env()

# LLM provider: Groq (primary) or OpenAI (optional fallback).
# Embeddings are NOT from an API - they come from the local HuggingFace model
# sentence-transformers/all-MiniLM-L6-v2 (see src/ingestion/embedder.py).
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENAI_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
EDUCATION_LINK = "https://www.amfiindia.com/investor"

NOT_FOUND_ANSWER = (
    "I don't have that information in my sources. My sources cover HDFC Mutual "
    "Fund scheme pages; for general mutual fund concepts you can check the "
    "AMFI investor page."
)

# Domain terms that must actually appear in the answer. If the user asks about
# one of these and the chosen sentence contains none of them, the chunk did not
# really answer the question -> report "not in sources" instead of quoting noise.
SALIENT_TERMS = (
    "expense ratio",
    "expense",
    "exit load",
    "sip",
    "minimum",
    "lump sum",
    "lock-in",
    "lock in",
    "riskometer",
    "benchmark",
    "capital gains statement",
    "statement",
    "download",
    "aum",
    "nav",
    "tax",
    "fund management",
    "manager",
)


def _groq_key() -> str | None:
    return os.getenv("GROQ_API_KEY")


def _openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY")


def _call_groq(messages: list[dict]) -> str:
    """Generate an answer using Groq (primary LLM provider)."""
    from groq import Groq

    client = Groq(api_key=_groq_key())
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        temperature=0,
        max_tokens=300,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def _call_openai(messages: list[dict]) -> str:
    """Optional fallback provider."""
    from openai import OpenAI

    client = OpenAI(api_key=_openai_key())
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        max_tokens=300,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def _extractive_answer(query: str, chunks: list[dict]) -> tuple[str, dict | None]:
    """Fallback when no LLM API key is configured.

    Picks the sentences with the strongest keyword overlap with the query
    across the retrieved chunks, so the snippet actually addresses the
    question. Returns (text, chunk_used) so the citation matches the fact.
    """
    if not chunks:
        return NOT_FOUND_ANSWER, None

    query_terms = {t for t in re.findall(r"[a-z0-9%]+", query.lower()) if len(t) > 2}
    stop = {"the", "and", "for", "what", "how", "fund", "hdfc", "is", "of", "a", "in", "my", "does", "do"}

    best_sentence, best_chunk, best_hits = "", None, -1
    for chunk in chunks:
        for sentence in _sentences(chunk["text"]):
            if len(sentence) < 25:
                continue
            low = sentence.lower()
            hits = sum(1 for t in query_terms if t not in stop and t in low)
            if hits > best_hits:
                best_sentence, best_chunk, best_hits = sentence, chunk, hits

    if best_hits <= 0:
        best_chunk = chunks[0]
        best_sentence = " ".join(_sentences(best_chunk["text"])[:2])

    # Relevance gate: the sentence must mention the domain term the user asked
    # about, otherwise we are quoting an unrelated chunk.
    query_low = query.lower()
    expected = [t for t in SALIENT_TERMS if t in query_low]
    if expected and not any(t in best_sentence.lower() for t in expected):
        return NOT_FOUND_ANSWER, None

    prefix = "(extractive mode - showing source text) "
    return prefix + _cap_sentences(best_sentence, max_sentences=3), best_chunk


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _cap_sentences(text: str, max_sentences: int = 3) -> str:
    """Enforce the <=3 sentence answer rule."""
    sentences = _sentences(text)
    kept = sentences[:max_sentences]
    if len(sentences) > max_sentences:
        kept[-1] = kept[-1].rstrip(".") + "."
    return " ".join(kept).strip()


# Some models echo their prompt's context markers back into the answer
# ("...is 0.76% [Context 1]" or "...0.76% 【2】"). We attach the citation
# ourselves, so any of these are noise to be removed before display.
_CONTEXT_MARKER = re.compile(
    r"\s*(?:\[\s*context\s*\d*\s*\]|【\s*context\s*\d*\s*】|\(\s*context\s*\d*\s*\)|"
    r"\*\*context\s*\d*\*\*|context\s*\d+\s*[:.-]|"
    # Bare numeric markers: 【2】, [2], 〈2〉, {2}
    r"[【\[\(〈{]\s*\d{1,2}\s*[】\]\)〉}])",
    re.IGNORECASE,
)


def _strip_context_markers(text: str) -> str:
    """Remove leaked context markers and tidy the leftover punctuation."""
    cleaned = _CONTEXT_MARKER.sub("", text)
    cleaned = re.sub(r"\s+([.,;:])", r"\1", cleaned)  # "0.76% ," -> "0.76%,"
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def generate_answer(query: str, chunks: list[dict]) -> dict:
    """Generate a grounded answer.

    Returns {"answer", "citation_url", "last_updated", "mode"}.
    """
    today = date.today().isoformat()

    if not chunks:
        return {
            "answer": NOT_FOUND_ANSWER,
            "citation_url": EDUCATION_LINK,
            "last_updated": today,
            "mode": "not-found",
        }

    citation_url = chunks[0]["source_url"]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(query, chunks)},
    ]

    if not (_groq_key() or _openai_key()):
        answer, used_chunk = _extractive_answer(query, chunks)
        return {
            "answer": answer,
            "citation_url": (used_chunk or chunks[0])["source_url"] if used_chunk else EDUCATION_LINK,
            "last_updated": today,
            "mode": "extractive" if used_chunk else "not-found",
        }

    # Groq first; OpenAI only if a key is configured.
    providers = [("groq", _call_groq)]
    if _openai_key():
        providers.append(("openai", _call_openai))

    answer, mode, errors = "", "extractive", []
    for provider_name, call in providers:
        try:
            raw = call(messages)
            answer = _cap_sentences(_strip_context_markers(raw)) or NOT_FOUND_ANSWER
            mode = provider_name
            break
        except Exception as err:  # noqa: BLE001 - never fail the demo on API errors
            errors.append(f"{provider_name}: {err}")
            print(f"  [generation] {provider_name} call failed -> {err}")

    if mode == "extractive":
        print("  [generation] falling back to extractive mode")
        answer, used_chunk = _extractive_answer(query, chunks)
        if used_chunk:
            citation_url = used_chunk["source_url"]

    return {"answer": answer, "citation_url": citation_url, "last_updated": today, "mode": mode}


if __name__ == "__main__":
    from src.retrieval.retriever import retrieve

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for q in ["What is the exit load of HDFC Mid Cap Fund?", "What is the ELSS lock-in period?"]:
        result = generate_answer(q, retrieve(q))
        print(f"\nQ: {q}\nA: {result['answer']}\nSource: {result['citation_url']}\nMode: {result['mode']}")
