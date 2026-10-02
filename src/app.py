"""Tiny Streamlit UI for the MF Scheme FAQ RAG chatbot.

Run: streamlit run src/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit puts src/ on sys.path, not the project root. Add the root so
# "from src.orchestrator import ask" resolves when run as src/app.py.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.orchestrator import ask  # noqa: E402

st.set_page_config(page_title="MF Scheme FAQ Assistant", page_icon="📊", layout="centered")

DISCLAIMER = "Facts-only. No investment advice."

EXAMPLE_QUESTIONS = [
    "What is the exit load of HDFC Mid Cap Fund?",
    "Minimum SIP for HDFC Flexi Cap (Direct, Growth)?",
    "What is the ELSS lock-in period?",
]

st.title("📊 Mutual Fund Scheme FAQ Assistant")
st.caption("HDFC Mutual Funds — answers drawn from public scheme pages only.")
st.warning(DISCLAIMER, icon="⚠️")

st.subheader("Try one of these:")
cols = st.columns(len(EXAMPLE_QUESTIONS))
for col, question in zip(cols, EXAMPLE_QUESTIONS):
    if col.button(question, key=f"example_{question[:20]}", use_container_width=True):
        st.session_state["query"] = question

query = st.text_input(
    "Ask a factual question",
    key="query",
    placeholder="e.g. What is the expense ratio of HDFC Large Cap Fund?",
)

if st.button("Ask", type="primary") and query:
    with st.spinner("Looking up the sources..."):
        result = ask(query)

    st.markdown("### Answer")
    if result["refused"]:
        st.info(result["answer"])
    else:
        st.write(result["answer"])

    st.markdown(f"**Source:** [{result['citation_url']}]({result['citation_url']})")
    st.caption(f"Last updated from sources: {result['last_updated']}")

st.divider()
st.caption(
    "This assistant shares published facts only and is not investment advice. "
    "It does not accept or store personal information such as PAN, Aadhaar, "
    "account numbers, OTPs, email addresses, or phone numbers."
)
