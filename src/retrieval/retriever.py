"""Retrieval: embed a query and pull the top-k chunks from ChromaDB."""

from __future__ import annotations

import os

from src.config import load_env
from src.ingestion.embedder import embed_query
from src.ingestion.vector_store import count
from src.ingestion.vector_store import query as vector_query

load_env()

import re  # noqa: E402

DEFAULT_K = int(os.getenv("TOP_K", "4"))

# Minimum top-1 similarity for a confident answer. Below this, the retriever
# reports "no relevant source" instead of forcing a weak match (our corpus is
# small and MiniLM similarities run low on some legitimate queries).
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.25"))

# Hybrid retrieval: dense similarity alone misses table rows like
# "Expense Ratio: 0.77" because a row of key-value pairs embeds close to
# everything else. Lexical overlap is added on top so an exact phrase in the
# question ("expense ratio") reliably pulls the row that contains it.
LEXICAL_BONUS = float(os.getenv("LEXICAL_BONUS", "0.35"))

STOPWORDS = {
    "what", "is", "the", "of", "for", "in", "a", "an", "and", "or", "to", "do",
    "does", "how", "my", "i", "me", "please", "tell", "give", "are", "was",
    "hdfc", "fund", "funds", "scheme", "mutual", "please",
}

# How many raw vector candidates to pull before re-ranking. All table rows look
# almost identical in embedding space, so a small pool can exclude the very row
# the lexical scorer would have ranked first. Our corpus is tiny (tens of
# chunks), so 0 = "re-rank every chunk in the collection", which is both cheap
# and immune to the dense-similarity lottery.
CANDIDATE_POOL = int(os.getenv("CANDIDATE_POOL", "0"))

# Phrases where an exact lexical hit is a strong signal.
PHRASES = (
    "expense ratio",
    "exit load",
    "lock in",
    "lock-in",
    "riskometer",
    "benchmark",
    "capital gains statement",
    "minimum sip",
    "lump sum",
    "minimum investment",
    "riskometer rating",
)


def _norm(text: str) -> str:
    """Collapse to alphanumeric only, so 'flexi cap' matches 'flexicap'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())

# Scheme name hints -> scheme substring used to boost/reorder results.
# Ordered longest-first: "large & mid cap" must be checked before "large cap"
# so "large cap" queries do not get boosted to HDFC Large & Mid Cap Fund.
SCHEME_KEYWORDS = {
    "large & mid cap": "Large & Mid Cap",
    "large and mid cap": "Large & Mid Cap",
    "large cap": "Large Cap",
    "flexi cap": "Flexi Cap",
    "flexi": "Flexi Cap",
    "equity fund": "Flexi Cap",
    "tax saver": "ELSS",
    "elss": "ELSS",
    "mid cap": "Mid Cap",
    "hdfc": "",  # generic, no reordering
}

# Spacing-insensitive aliases used by the lexical scorer.
SCHEME_ALIASES = (
    "large & mid cap",
    "large cap",
    "flexi cap",
    "mid cap",
    "elss",
    "tax saver",
    "sensex",
    "nifty 50",
    "balanced advantage",
    "multi cap",
    "small cap",
    "pharma",
)


def _scheme_hint(query: str) -> str:
    lowered = query.lower()
    for keyword, scheme in SCHEME_KEYWORDS.items():
        if keyword in lowered and scheme:
            return scheme
    return ""


def _matches_hint(result_scheme: str, hint: str) -> bool:
    """Exact scheme-name match, so 'Large Cap' never matches 'Large & Mid Cap'."""
    return hint.lower() in result_scheme.lower()


def _terms(text: str) -> set[str]:
    """Content words, with glued scheme names split ('flexicap' -> flexi, cap)."""
    lowered = text.lower()
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", lowered):
        if len(token) > 2 and token not in STOPWORDS:
            tokens.add(token)
        if len(token) > 6:
            for alias in SCHEME_ALIASES:
                parts = alias.lower().split()
                if len(parts) > 1 and "".join(parts) == token:
                    tokens.update(p for p in parts if len(p) > 2)
    return tokens


def _segments(chunk_text: str) -> list[str]:
    """Split labelled table text into per-fund pieces.

    The loader renders each table row as 'Fund Name: X | Category: Y | ...', so
    splitting on 'Fund Name:' isolates one scheme's facts. Without this, a chunk
    holding five rows matches every scheme equally and the retriever cannot tell
    which row answers the question. Returns [chunk_text] for prose chunks.
    """
    if "Fund Name:" not in chunk_text:
        return [chunk_text]
    segments = re.split(r"Fund Name:", chunk_text)
    # Keep the leading header block with the first row so column names stay in play.
    return [segments[0] + segments[1]] + segments[2:]


def _segment_score(query: str, segment: str, hint: str) -> float:
    """Score one segment: term overlap, domain-phrase hits, scheme-name fit."""
    q_terms = _terms(query)
    if not q_terms:
        return 0.0
    c_terms = _terms(segment)
    score = len(q_terms & c_terms) / len(q_terms)

    q_low, c_low = query.lower(), segment.lower()
    for phrase in PHRASES:
        if phrase in q_low and phrase in c_low:
            score += 0.3

    if hint:
        if _norm(hint) in _norm(segment):
            score += 0.25
        elif hint.lower().split() and set(_terms(hint)) <= c_terms:
            # Words present but not as the asked scheme: "Large Cap" matching the
            # "Large & Mid Cap Fund" row is a near miss, not a hit.
            score -= 0.25

    return max(score, 0.0)


def _lexical_score(query: str, chunk_text: str, hint: str = "") -> float:
    """Best score across the chunk's segments (a chunk may hold several rows)."""
    return max(_segment_score(query, seg, hint) for seg in _segments(chunk_text))


SCHEME_BOOST = float(os.getenv("SCHEME_BOOST", "0.12"))


def retrieve(query: str, k: int = DEFAULT_K) -> list[dict]:
    """Return top-k chunks [{text, source_url, scheme, score}] for a query.

    Ranking is hybrid: dense cosine similarity from ChromaDB, re-scored with a
    lexical pass. Dense similarity alone cannot separate the labelled table rows
    on the AMC page (they are near-identical key-value strings), so the lexical
    pass decides which row actually answers the question. Chunks whose *page*
    metadata matches the scheme named in the question get a small bonus, which
    keeps the cited page aligned with the scheme asked about.

    Returns [] when the best match is below MIN_SCORE, signalling the
    orchestrator to answer "not available in my sources".
    """
    pool = count()
    n_candidates = pool if CANDIDATE_POOL <= 0 else min(CANDIDATE_POOL, pool)
    results = vector_query(embed_query(query), k=n_candidates)
    if not results:
        return []

    hint = _scheme_hint(query)
    for r in results:
        bonus = LEXICAL_BONUS * _lexical_score(query, r["text"], hint)
        if hint and _matches_hint(r["scheme"], hint) and _norm(hint) not in _norm(r["text"]):
            # Page metadata matches and the chunk is prose (no table row naming a
            # different scheme), so the scheme page itself is the right source.
            bonus += SCHEME_BOOST
        r["score"] += bonus

    results.sort(key=lambda r: r["score"], reverse=True)
    for r in results:
        r["score"] = round(r["score"], 4)

    results = results[:k]

    if results and results[0]["score"] < MIN_SCORE:
        print(f"  [retriever] top score {results[0]['score']} < {MIN_SCORE} -> no confident match")
        return []

    return results
