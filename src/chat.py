"""Interactive terminal chat for testing the assistant without the UI.

Run: python -m src.chat
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from src.config import load_env

load_env()

from src.orchestrator import ask  # noqa: E402

BANNER = """
==========================================================
 HDFC Mutual Fund FAQ Assistant - terminal test
 Facts-only. No investment advice.
 Type a question, or 'exit' to quit.
==========================================================
"""


def _key_status() -> str:
    if os.getenv("GROQ_API_KEY"):
        return f"GROQ_API_KEY found (model: {os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')})"
    if os.getenv("OPENAI_API_KEY"):
        return f"OPENAI_API_KEY found (model: {os.getenv('LLM_MODEL', 'gpt-4o-mini')})"
    return "NO LLM KEY FOUND - answers will show source text (extractive mode)"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print(BANNER)
    print(f"Key status: {_key_status()}\n")

    print("Loading the embedding model (first run takes ~15s)...")
    ask("warmup")  # trigger model load before the first real question
    print("Ready.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit", "q"}:
            print("Bye.")
            break

        result = ask(query)
        tag = "REFUSED" if result["refused"] else result["mode"]
        print(f"\nAssistant [{tag}]:\n{result['response']}\n")


if __name__ == "__main__":
    main()
