"""Manual sanity check for the retriever.

Run: python -m src.retrieval.test_retrieve
"""

from __future__ import annotations

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.retrieval.prompts import build_user_prompt  # noqa: E402
from src.retrieval.retriever import retrieve  # noqa: E402

SAMPLE_QUERIES = [
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "What is the ELSS lock-in period?",
    "How do I download a capital gains statement?",
]


def main() -> None:
    for query in SAMPLE_QUERIES:
        print("=" * 70)
        print(f"QUERY: {query}")
        chunks = retrieve(query)
        for rank, chunk in enumerate(chunks, start=1):
            print(f"\n  #{rank} [{chunk['score']}] {chunk['scheme']}")
            print(f"      {chunk['source_url']}")
            print(f"      {chunk['text'][:200]}...")
        print("\n--- Built prompt (first 600 chars) ---")
        print(build_user_prompt(query, chunks)[:600])


if __name__ == "__main__":
    main()
