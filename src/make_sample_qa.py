"""Generate sample_qa.md by running queries through the orchestrator.

Run: python -m src.make_sample_qa
"""

from __future__ import annotations

import sys
from datetime import date

from src.orchestrator import ask

QUERIES = [
    "What is the exit load of HDFC Mid Cap Fund?",
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "What is the expense ratio of HDFC Flexi Cap Direct Growth?",
    "What is the minimum SIP for HDFC Flexi Cap Direct Growth?",
    "What is the NAV of HDFC Mid Cap Fund?",
    "Who manages the HDFC Mid Cap Fund?",
    # Below: facts genuinely absent from the reachable corpus. Kept so the
    # sample shows honest "not in my sources" behaviour, not only happy paths.
    "What is the ELSS lock-in period?",
    "How do I download a capital gains statement?",
    # Advice questions must be refused.
    "Should I buy HDFC ELSS now?",
    "Which mutual fund is best for me?",
]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    lines = [
        "# Sample Q&A",
        "",
        f"Generated on {date.today().isoformat()} by `python -m src.make_sample_qa`.",
        "",
        "> Answers are produced by the RAG assistant end-to-end: guardrails -> retrieval -> generation.",
        "> Every entry shows the single source link the assistant attaches to the answer.",
        "",
    ]

    for i, query in enumerate(QUERIES, start=1):
        result = ask(query)
        label = "REFUSED" if result["refused"] else result["mode"].upper()
        lines += [
            f"## {i}. {query}",
            "",
            f"- **Result type:** {label}",
            f"- **Answer:** {result['answer']}",
            f"- **Source:** {result['citation_url']}",
            f"- **Last updated from sources:** {result['last_updated']}",
            "",
        ]
        print(f"[{i}/{len(QUERIES)}] {query} -> {label}")

    with open("sample_qa.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\nWrote sample_qa.md")


if __name__ == "__main__":
    main()
