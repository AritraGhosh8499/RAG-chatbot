"""End-to-end query handling: guardrails -> retrieval -> generation -> formatted answer."""

from __future__ import annotations

import sys

from src.generation import generate_answer
from src.guardrails import is_advice_query, refusal_message
from src.retrieval.retriever import retrieve

FALLBACK_EDUCATION_LINK = "https://www.amfiindia.com/investor"


def format_response(result: dict) -> str:
    """Format a generated result into the final user-facing response."""
    return (
        f"{result['answer']}\n\n"
        f"Source: {result['citation_url']}\n"
        f"Last updated from sources: {result['last_updated']}"
    )


def ask(query: str) -> dict:
    """Handle a user query end-to-end.

    Returns {"response", "answer", "citation_url", "last_updated", "mode", "refused"}.
    """
    query = (query or "").strip()
    if not query:
        return {
            "response": "Please type a factual question about HDFC mutual fund schemes.\n\n"
            f"Source: {FALLBACK_EDUCATION_LINK}\nLast updated from sources: n/a",
            "answer": "",
            "citation_url": FALLBACK_EDUCATION_LINK,
            "last_updated": "n/a",
            "mode": "empty",
            "refused": False,
        }

    if is_advice_query(query):
        refusal = refusal_message()
        return {
            "response": f"{refusal}\n\nSource: {FALLBACK_EDUCATION_LINK}\nLast updated from sources: n/a",
            "answer": refusal,
            "citation_url": FALLBACK_EDUCATION_LINK,
            "last_updated": "n/a",
            "mode": "refusal",
            "refused": True,
        }

    chunks = retrieve(query)
    result = generate_answer(query, chunks)
    return {**result, "response": format_response(result), "refused": False}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        queries = [
            "What is the exit load of HDFC Mid Cap Fund?",
            "What is the expense ratio of HDFC Large Cap Fund?",
            "Minimum SIP for HDFC Flexi Cap?",
            "What is the ELSS lock-in period?",
            "How do I download a capital gains statement?",
            "Should I buy HDFC ELSS now?",
        ]

    for q in queries:
        result = ask(q)
        print("=" * 72)
        print(f"Q: {q}")
        print(f"[mode={result['mode']} refused={result['refused']}]")
        print(result["response"])


if __name__ == "__main__":
    main()
