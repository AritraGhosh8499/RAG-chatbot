"""Guardrails: refuse advice / opinionated queries before retrieval."""

from __future__ import annotations

import re

# Educational link shown with refusals (AMFI investor page, verified reachable)
EDUCATION_LINK = "https://www.amfiindia.com/investor"

REFUSAL_TEMPLATE = (
    "I can only share published facts about mutual fund schemes — I can't give "
    "personalised or investment advice. For guidance on choosing or reviewing "
    "investments, please read general investor education material: {link}"
)

# Patterns that indicate a recommendation / opinion / portfolio request
_ADVICE_PATTERNS = [
    r"\bshould\s+(i|we|you)\b",
    r"\bshould\s+(i\s+)?(buy|sell|invest|subscribe|redeem|switch|exit)\b",
    r"\b(buy|sell|invest|purchase)\b.*\b(now|good time|bad time|right time|timing)\b",
    r"\bis\s+it\s+(a\s+)?(good|bad|safe|right|worth)\b",
    r"\b(is|are)\s+(\w+\s+){1,4}(a\s+)?(good|bad|safe|risky|worth)\s+(investment|fund|scheme|option|choice)\b",
    r"\b(is|are)\s+(hdfc|this|the)\b.*\bbest\b",
    r"\bbest\s+(fund|scheme|mutual\s+fund)\b",
    r"\bwhich\s+(fund|scheme|mutual\s+fund)\b",
    r"\b(recommend|suggest)\b",
    r"\bworth\s+(it|investing)\b",
    r"\b(my|our)\s+portfolio\b",
    r"\b(portfolio|allocation|asset\s+allocation)\b.*\b(for|should)\b",
    r"\bcompare\b.*\b(returns|performance|growth)\b",
    r"\bwhich\s+performs?\s+better\b",
    r"\b(better|higher|lower)\s+returns?\b",
    r"\b(is|are)\s+.*\bsafe\s+to\s+invest\b",
    r"\bhold\b.*\b(for|how long)\b",
    r"\bsip\b.*\b(plan|amount|monthly)\b.*\b(should|i)\b",
]

_ADVICE_RE = re.compile("|".join(_ADVICE_PATTERNS), re.IGNORECASE)


def is_advice_query(query: str) -> bool:
    """Return True if the query asks for advice/opinion/comparison."""
    return bool(_ADVICE_RE.search(query or ""))


def refusal_message() -> str:
    """Polite facts-only refusal with an educational link."""
    return REFUSAL_TEMPLATE.format(link=EDUCATION_LINK)


# ---------------------------------------------------------------------------
# Example test cases
# ---------------------------------------------------------------------------
SHOULD_REFUSE = [
    "Should I buy HDFC ELSS now?",
    "Which is the best mutual fund for me?",
    "Is HDFC Mid Cap Fund a good investment?",
    "Compare the returns of HDFC Large Cap vs HDFC Flexi Cap",
    "Suggest a portfolio for me",
]

SHOULD_PASS = [
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "What is the ELSS lock-in period?",
    "Minimum SIP for HDFC Flexi Cap?",
    "How do I download a capital-gains statement?",
    "What is the exit load and benchmark of HDFC Large Cap Fund?",
]


def _self_test() -> None:
    failures = []
    for q in SHOULD_REFUSE:
        caught = is_advice_query(q)
        print(f"{'PASS' if caught else 'FAIL'} (refuse) :: {q}")
        if not caught:
            failures.append(q)
    for q in SHOULD_PASS:
        caught = is_advice_query(q)
        print(f"{'PASS' if not caught else 'FAIL'} (allow)  :: {q}")
        if caught:
            failures.append(q)

    if failures:
        raise SystemExit(f"\n{len(failures)} test case(s) failed")
    print("\nAll guardrail test cases passed.")


if __name__ == "__main__":
    _self_test()
    print("\nRefusal message:\n" + refusal_message())
