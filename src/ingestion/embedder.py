"""Embedding model wrapper (sentence-transformers/all-MiniLM-L6-v2)."""

from __future__ import annotations

import os

from sentence_transformers import SentenceTransformer

from src.config import load_env

load_env()

# PRD: embedding model = sentence-transformers/all-MiniLM-L6-v2 (local, no API key)
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Load the embedding model once (module-level singleton)."""
    global _model
    if _model is None:
        print(f"Loading embedding model: {MODEL_NAME}")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts into vectors."""
    if not texts:
        return []
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    return [list(map(float, vec)) for vec in embeddings]


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]


if __name__ == "__main__":
    vec = embed_query("What is the expense ratio of HDFC Mid Cap Fund?")
    print(f"Query embedding dims: {len(vec)}")
