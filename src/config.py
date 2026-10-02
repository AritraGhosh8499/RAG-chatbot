"""Environment loading shared across the app.

Primary file: .env
Fallback: .env.example (so a key placed there still works, e.g. during setup)

Note: .env is the correct place for secrets. .env.example is normally committed
to version control, so keep real keys out of it once .env exists.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

_ENV_LOADED = False


def load_env() -> None:
    """Load .env, falling back to .env.example if no key is present."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    load_dotenv(os.path.join(root, ".env"))
    if not (os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY")):
        fallback = os.path.join(root, ".env.example")
        if os.path.exists(fallback):
            load_dotenv(fallback)
