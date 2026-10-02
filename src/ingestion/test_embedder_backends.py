"""Prove the ONNX backend produces the same vectors as the torch backend.

Retrieval quality depends on this, so it is checked rather than assumed:
every vector is compared with cosine similarity against the PyTorch original.
"""

import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROBES = [
    "What is the expense ratio of HDFC Mid Cap Fund?",
    "exit load HDFC Flexi Cap Fund Direct Growth",
    "Fund Name: HDFC Mid Cap Fund (Direct, Growth)\nExpense ratio: 0.76 %",
    "ELSS lock in period three years",
    "minimum SIP amount for HDFC Large Cap Fund",
]


def run(backend: str) -> list[list[float]]:
    """Embed the probes in a clean subprocess so both backends stay unloaded
    at the same time (torch and onnxruntime together would defeat the point)."""
    env = dict(os.environ, EMBEDDER_BACKEND=backend, PYTHONIOENCODING="utf-8")
    code = (
        "import json,sys;"
        "from src.ingestion.embedder import embed_texts, backend_name;"
        f"p=json.dumps({PROBES!r});"
        "sys.stdout.reconfigure(encoding='utf-8');"
        "print('BACKEND:'+backend_name());"
        "print('VECS:'+json.dumps(embed_texts(json.loads(p))))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, encoding="utf-8"
    )
    if out.returncode != 0:
        print(out.stdout[-2000:])
        print(out.stderr[-3000:])
        raise SystemExit(f"{backend} backend failed")
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith(("BACKEND:", "VECS:"))]
    import json

    backend = next(ln[8:] for ln in lines if ln.startswith("BACKEND:"))
    vecs = json.loads(next(ln[5:] for ln in lines if ln.startswith("VECS:")))
    print(f"{backend} backend reported itself as: {backend}")
    return vecs


print("=== reference: PyTorch / sentence-transformers ===")
torch_vecs = run("torch")

print("\n=== new: ONNX Runtime ===")
onnx_vecs = run("onnx")

print("\n=== agreement ===")
worst = 1.0
for probe, t_vec, o_vec in zip(PROBES, torch_vecs, onnx_vecs):
    dot = sum(a * b for a, b in zip(t_vec, o_vec))
    tn = sum(a * a for a in t_vec) ** 0.5
    on = sum(b * b for b in o_vec) ** 0.5
    cos = dot / (tn * on)
    worst = min(worst, cos)
    print(f"  cos={cos:.6f}  dims={len(o_vec)}  {probe[:58]}")
    assert len(o_vec) == len(t_vec) == 384, "dimension mismatch"

print(f"\nworst cosine similarity: {worst:.6f}")
assert worst > 0.999, f"ONNX and torch disagree too much: {worst}"
print("PASS - ONNX reproduces the PyTorch vectors (cos > 0.999 on every probe)")
