"""Persistent ChromaDB vector store for MF FAQ chunks."""

from __future__ import annotations

import os
import re
from pathlib import Path

import chromadb
from chromadb.config import Settings

from src.config import load_env

load_env()

CHROMA_DIR = Path(os.getenv("CHROMA_DIR") or (Path(__file__).resolve().parents[2] / "chroma_db"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "mf_faq")
AMC = os.getenv("AMC_NAME", "HDFC")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def get_collection(reset: bool = False):
    """Open (or recreate) the persistent ChromaDB collection."""
    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )

    if reset:
        try:
            # Drop the collection in place. Deleting the directory on Windows
            # fails while this client holds chroma.sqlite3 open, so the
            # collection API is the reliable route.
            client.delete_collection(COLLECTION_NAME)
            print(f"  [vector_store] dropped collection '{COLLECTION_NAME}'")
        except Exception:
            pass  # nothing to drop (first run)

    return client.get_or_create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def upsert_chunks(chunks: list[dict], embeddings: list[list[float]], reset: bool = False) -> None:
    """Store chunks + embeddings + metadata into ChromaDB."""
    collection = get_collection(reset=reset)

    ids, documents, metadatas, embeds = [], [], [], []
    for chunk, embedding in zip(chunks, embeddings):
        chunk_id = f"{_slug(chunk['scheme'])}_chunk_{chunk['chunk_id']}"
        ids.append(chunk_id)
        documents.append(chunk["text"])
        metadatas.append(
            {
                "source_url": chunk["url"],
                "scheme": chunk["scheme"],
                "amc": AMC,
                "chunk_id": chunk["chunk_id"],
            }
        )
        embeds.append(embedding)

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeds)
        print(f"Upserted {len(ids)} records into '{COLLECTION_NAME}' at {CHROMA_DIR}")


def query(embedding: list[float], k: int = 4) -> list[dict]:
    """Similarity search; returns list of {text, source_url, scheme, score}."""
    collection = get_collection()
    results = collection.query(query_embeddings=[embedding], n_results=k)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    out: list[dict] = []
    for text, meta, dist in zip(docs, metas, dists):
        out.append(
            {
                "text": text,
                "source_url": meta.get("source_url"),
                "scheme": meta.get("scheme"),
                "score": round(1 - dist, 4),  # cosine distance -> similarity
            }
        )
    return out


def count() -> int:
    return get_collection().count()


if __name__ == "__main__":
    print(f"Records in collection: {count()}")
