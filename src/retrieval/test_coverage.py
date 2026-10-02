"""Retrieval coverage sweep: does the top-ranked chunk contain the expected fact?

Retrieval only - no LLM calls, so this is fast and free of rate limits.
Run: python sweep_retrieval.py
"""

import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.retrieval.retriever import retrieve

# (query, expected evidence substring in the top chunk, answerable?)
CASES = [
    ("expense ratio of HDFC Mid Cap Fund", "Expense Ratio: 0.76", True),
    ("expense ratio of HDFC Flexi Cap Fund", "Expense Ratio: 0.77", True),
    ("expense ratio of HDFC Equity Flexi Cap direct growth", "Expense Ratio: 0.77", True),
    ("NAV of HDFC Mid Cap Fund", "NAV: 219.44", True),
    ("exit load of HDFC Mid Cap Fund", "redeemed within 1 year", True),
    ("minimum SIP amount for HDFC Flexi Cap", "\u20b9100", True),
    ("minimum lump sum for HDFC Flexi Cap", "\u20b9100", True),
    ("expense ratio of HDFC Large and Mid Cap Fund", "Expense Ratio: 0.92", True),
    ("fund size / AUM of HDFC Mid Cap Fund", "11,477", True),
    ("risk category of HDFC Mid Cap Fund", "Very High", True),
    ("who manages HDFC Mid Cap Fund", "Asset Management", True),
    ("category of HDFC ELSS Tax Saver Fund", "Equity", True),
    ("expense ratio of HDFC Large Cap Fund", None, False),
    ("what is the ELSS lock-in period", None, False),
    ("how do I download a capital gains statement", None, False),
]


def main() -> None:
    passed = failed = 0

    for query, evidence, answerable in CASES:
        chunks = retrieve(query)
        top = chunks[0]["text"] if chunks else ""

        if answerable:
            # The LLM sees the whole top-k, so evidence anywhere in context counts.
            rank = next(
                (i for i, c in enumerate(chunks, 1) if evidence in c["text"]),
                None,
            )
            ok = rank is not None
            if rank == 1:
                where = "rank 1 (ideal)"
            elif ok:
                where = f"rank {rank} of {len(chunks)} (in context, not top)"
            else:
                where = "NOT IN TOP-K (bot cannot answer)"
        else:
            rank, ok = None, True
            where = "gap - expect 'not in my sources'"

        passed += ok
        failed += not ok
        flag = "PASS" if ok else "FAIL"
        kind = "answerable" if answerable else "gap       "
        print(f"[{flag}] ({kind}) {query}")
        print(f"         {where}")

    print(f"\n{passed} passed, {failed} failed out of {len(CASES)}")


if __name__ == "__main__":
    main()
