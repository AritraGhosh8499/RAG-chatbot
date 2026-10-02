"""Entry point for the ingestion pipeline.

Usage:
    python -m src.ingestion.run_ingest --step load
"""

from __future__ import annotations

import argparse
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.ingestion.chunker import chunk_pages
from src.ingestion.embedder import embed_texts
from src.ingestion.loader import CORPUS, load_all
from src.ingestion.vector_store import count, upsert_chunks
from src.retrieval.retriever import retrieve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ingestion pipeline steps.")
    parser.add_argument("--step", choices=["load", "chunk", "embed", "query"], default="load")
    parser.add_argument("--query", help="Query text for --step query")
    parser.add_argument("--reset", action="store_true", help="Recreate the ChromaDB collection")
    args = parser.parse_args()

    if args.step == "load":
        pages = load_all(CORPUS)
        print("\n=== Load step summary ===")
        for page in pages:
            print(f"{page['scheme']}: {len(page['text'])} chars from {page['url']}")
        total = sum(len(p["text"]) for p in pages)
        print(f"Total: {total} chars across {len(pages)} pages")

    elif args.step == "chunk":
        pages = load_all(CORPUS)
        chunks = chunk_pages(pages)
        print(f"\nTotal chunks: {len(chunks)}")
        print("\n=== Sample chunks ===")
        for c in chunks[:3]:
            print(f"--- {c['scheme']} | chunk {c['chunk_id']} | {len(c['text'])} chars ---")
            print(c["text"][:300], "\n")

    elif args.step == "query":  # uses the real retriever, same as the bot
        sample = args.query or "What is the expense ratio of HDFC Mid Cap Fund?"
        for r in retrieve(sample):
            print(f"[{r['score']}] {r['scheme']} :: {r['text'][:160]}")

    elif args.step == "embed":
        pages = load_all(CORPUS)
        chunks = chunk_pages(pages)
        embeddings = embed_texts([c["text"] for c in chunks])
        upsert_chunks(chunks, embeddings, reset=args.reset)
        print(f"\nRecords in collection: {count()}")
        print("\n=== Sample retrieval ===")
        for r in retrieve("What is the expense ratio of HDFC Mid Cap Fund?"):
            print(f"[{r['score']}] {r['scheme']} :: {r['text'][:160]}")


if __name__ == "__main__":
    main()
