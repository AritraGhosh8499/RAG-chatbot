"""Fetch and clean the public pages used as the RAG corpus."""

from __future__ import annotations

import re
import time

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Manifest of corpus URLs + friendly scheme names (from docs/PRD.md)
# Note: HDFC's own site (hdfcmf.com / hdfcaml.com) is unreachable from the demo
# network (connect timeout), so the official AMFI investor page is used for
# general mutual fund fundamentals. See data/sources.md for the full record.
CORPUS: list[dict] = [
    {"url": "https://groww.in/mutual-funds/amc/hdfc-mutual-funds", "scheme": "HDFC Mutual Funds (AMC Overview)"},
    {"url": "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth", "scheme": "HDFC Large Cap Fund (Direct, Growth)"},
    {"url": "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth", "scheme": "HDFC Equity Fund - Flexi Cap (Direct, Growth)"},
    {"url": "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth", "scheme": "HDFC ELSS Tax Saver Fund (Direct, Growth)"},
    {"url": "https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth", "scheme": "HDFC Mid Cap Fund (Direct, Growth)"},
    {"url": "https://www.amfiindia.com/investor", "scheme": "AMFI Investor Corner (Mutual Fund Fundamentals)"},
]

_STRIP_TAGS = ["script", "style", "nav", "footer", "header", "form", "noscript", "iframe"]
_CONTENT_SELECTORS = ["h1", "h2", "h3", "h4", "p", "li", "td", "th"]


def fetch_page(url: str, timeout: int = 20, retries: int = 3, backoff: float = 2.0) -> str:
    """GET a page's HTML with a browser-like User-Agent, timeout, and retries."""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as err:  # noqa: BLE001 - retry on any network/HTTP error
            last_err = err
            print(f"  [retry {attempt}/{retries}] {url}: {err}")
            time.sleep(backoff * attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def _looks_numeric(value: str) -> bool:
    """True if a cell looks like data (number, %, currency) rather than a label."""
    v = value.strip().lower()
    if not v:
        return True
    if re.fullmatch(r"[₹$€]?[\d,.]+\s*(%cr|%|cr)?", v):
        return True
    return v in {"--", "-", "n/a", "na", "view all"}


def _table_to_text(table) -> list[str]:
    """Render an HTML table as labelled key-value lines.

    Source tables (e.g. the HDFC scheme list) have a header row plus rows of
    bare numbers. Flattening them loses the column meaning, so a chunk holding
    "0.77" could be NAV, rating or expense ratio. Emitting
    "Expense Ratio: 0.77" keeps the fact self-describing and retrievable.
    """
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)
    if not rows:
        return []

    # Use the first row as the header only when it looks like labels.
    header: list[str] = []
    if len(rows[0]) >= 2 and not any(_looks_numeric(c) for c in rows[0]):
        header = rows[0]
        rows = rows[1:]

    lines: list[str] = []
    if header:
        lines.append("Table columns: " + ", ".join(header))
    for cells in rows:
        labelled = []
        for i, value in enumerate(cells):
            name = header[i] if i < len(header) else ""
            labelled.append(f"{name}: {value}" if name else value)
        lines.append(" | ".join(labelled))
    return lines


def clean_html(html: str) -> str:
    """Strip boilerplate and extract headings/paragraphs/list/table text."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    parts: list[str] = []

    # Tables first: render them as labelled rows, then remove them so their
    # cells are not also dumped as unlabelled text.
    for table in soup.find_all("table"):
        table_lines = _table_to_text(table)
        if table_lines:
            parts.extend(table_lines)
        table.decompose()

    for el in soup.find_all(_CONTENT_SELECTORS):
        text = el.get_text(" ", strip=True)
        if text:
            parts.append(text)

    # De-duplicate adjacent duplicates (pages often repeat table cells in p and li)
    seen: set[str] = set()
    unique_parts: list[str] = []
    for part in parts:
        key = re.sub(r"\s+", " ", part).lower()
        if key not in seen:
            seen.add(key)
            unique_parts.append(part)

    return "\n".join(unique_parts)


def load_all(urls: list[dict] | None = None) -> list[dict]:
    """Fetch + clean every page in the corpus.

    Returns a list of {"url", "scheme", "text"}.
    """
    pages = urls if urls is not None else CORPUS
    results: list[dict] = []
    for item in pages:
        print(f"Fetching: {item['url']}")
        html = fetch_page(item["url"])
        text = clean_html(html)
        results.append({"url": item["url"], "scheme": item["scheme"], "text": text})
        print(f"  -> {len(text)} chars extracted")
    return results


if __name__ == "__main__":
    for page in load_all():
        print(f"{page['scheme']}: {len(page['text'])} chars")
