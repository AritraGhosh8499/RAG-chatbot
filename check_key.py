"""Safely check whether the Groq key is present in .env / .env.example.

Prints a masked value only. Run: python check_key.py
"""

import os

for path in (".env", ".env.example"):
    if not os.path.exists(path):
        print(f"{path}: not found")
        continue
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            stripped = line.strip()
            if stripped.startswith("GROQ_API_KEY"):
                value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                masked = (value[:6] + "..." + value[-4:]) if len(value) > 12 else repr(value)
                print(f"{path} line {i}: GROQ_API_KEY = {masked}  (length {len(value)})")
            elif stripped.startswith("GROQ_MODEL"):
                print(f"{path} line {i}: {stripped}")
