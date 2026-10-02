"""Embedding wrapper for sentence-transformers/all-MiniLM-L6-v2.

Two interchangeable backends produce the same 384-dimension vectors:

  onnx  (default)  onnxruntime + tokenizers. The 86 MB fp32 ONNX graph runs
                   without PyTorch, which is what keeps the process inside a
                   512 MB free-tier container. Measured peak RSS: ~250 MB
                   versus ~680 MB for the torch backend.
  torch (fallback) sentence-transformers, i.e. the original PyTorch path. Kept
                   as a fallback so a machine without onnxruntime still runs.

Select with EMBEDDER_BACKEND=onnx|torch (default: onnx). Both paths mean-pool
over the attention mask and L2-normalise, matching the model's
`1_Pooling/config.json` (pooling_mode_mean_tokens = true).

Why this matters: PyTorch alone costs ~194 MB of RAM on import, and holding the
MiniLM weights inside it costs a further ~340 MB. That is what pushed the app
over Render's free-tier limit. The ONNX graph is the same weights, in a runtime
that does not reserve those arenas.
"""

from __future__ import annotations

import os
from typing import Any

from src.config import load_env

load_env()

# PRD: embedding model = sentence-transformers/all-MiniLM-L6-v2 (local, no API key)
MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
MAX_TOKENS = int(os.getenv("EMBEDDER_MAX_TOKENS", "256"))
BATCH_SIZE = int(os.getenv("EMBEDDER_BATCH_SIZE", "16"))
PREFERRED_BACKEND = os.getenv("EMBEDDER_BACKEND", "onnx").strip().lower()

_state: dict[str, Any] = {}


def backend_name() -> str:
    """Which backend is actually in use (may differ from the preference)."""
    if "backend" not in _state:
        _ensure_backend()
    return _state["backend"]


def _load_onnx() -> dict[str, Any]:
    import numpy as np
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    print(f"Loading embedding model (onnx): {MODEL_NAME}")
    model_path = hf_hub_download(MODEL_NAME, "onnx/model.onnx")
    tok_path = hf_hub_download(MODEL_NAME, "tokenizer.json")

    # onnxruntime grabs threads and large arena blocks by default; both are
    # wasted memory in a small container, and there is only one request at a time.
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.getenv("EMBEDDER_THREADS", "1"))
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    session = ort.InferenceSession(
        model_path, sess_options=opts, providers=["CPUExecutionProvider"]
    )
    tokenizer = Tokenizer.from_file(tok_path)
    tokenizer.enable_truncation(max_length=MAX_TOKENS)
    tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")

    input_names = {i.name for i in session.get_inputs()}
    output_names = {o.name for o in session.get_outputs()}

    return {
        "backend": "onnx",
        "np": np,
        "session": session,
        "tokenizer": tokenizer,
        "input_names": input_names,
        "hidden_name": "last_hidden_state" if "last_hidden_state" in output_names else session.get_outputs()[0].name,
    }


def _load_torch() -> dict[str, Any]:
    from sentence_transformers import SentenceTransformer

    print(f"Loading embedding model (torch): {MODEL_NAME}")
    return {"backend": "torch", "model": SentenceTransformer(MODEL_NAME)}


def _ensure_backend() -> None:
    """Pick a backend once: the preference if it loads, otherwise the fallback."""
    if _state:
        return

    if PREFERRED_BACKEND == "onnx":
        try:
            _state.update(_load_onnx())
            return
        except Exception as err:  # noqa: BLE001 - fall back rather than fail
            print(f"  [embedder] onnx backend unavailable ({err}); using torch")
    elif PREFERRED_BACKEND == "torch":
        try:
            _state.update(_load_torch())
            return
        except Exception as err:  # noqa: BLE001
            print(f"  [embedder] torch backend unavailable ({err}); using onnx")

    # Preference was explicit but failed, or neither was named: try both.
    for loader in (_load_onnx, _load_torch):
        try:
            _state.update(loader())
            return
        except Exception as err:  # noqa: BLE001
            print(f"  [embedder] {loader.__name__} failed: {err}")

    raise RuntimeError("No embedding backend could be loaded (onnx and torch both failed).")


def _mean_pool(hidden, mask, np):
    """Average token vectors, ignoring padding.

    Mirrors sentence-transformers mean pooling: weight each token by its
    attention mask so padded positions contribute nothing, then divide by the
    number of real tokens.
    """
    mask_f = mask[:, :, None].astype(hidden.dtype)
    summed = (hidden * mask_f).sum(axis=1)
    counts = np.clip(mask_f.sum(axis=1), a_min=1e-9, a_max=np.inf)
    return summed / counts


def _embed_onnx(texts: list[str], st: dict[str, Any]) -> list[list[float]]:
    np = st["np"]
    session = st["session"]
    tokenizer = st["tokenizer"]

    out: list[list[float]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        encodings = tokenizer.encode_batch(batch)

        # This graph exports a third optional input, token_type_ids.
        feeds = {
            "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
        }
        if "token_type_ids" in st["input_names"]:
            feeds["token_type_ids"] = np.array([e.type_ids for e in encodings], dtype=np.int64)

        hidden = session.run([st["hidden_name"]], feeds)[0]
        pooled = _mean_pool(hidden, feeds["attention_mask"], np)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1.0, norms)  # avoid dividing an all-zero row
        out.extend((pooled / norms).astype(np.float32).tolist())

        print(f"  [embedder] {min(start + BATCH_SIZE, len(texts))}/{len(texts)}", end="\r", flush=True)
    if texts:
        print()
    return out


def _embed_torch(texts: list[str], st: dict[str, Any]) -> list[list[float]]:
    vectors = st["model"].encode(texts, show_progress_bar=True, convert_to_numpy=True)
    return [list(map(float, vec)) for vec in vectors]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts into L2-normalised 384-d vectors."""
    if not texts:
        return []
    _ensure_backend()
    if _state["backend"] == "onnx":
        return _embed_onnx(texts, _state)
    return _embed_torch(texts, _state)


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]


if __name__ == "__main__":
    vec = embed_query("What is the expense ratio of HDFC Mid Cap Fund?")
    print(f"Backend:      {backend_name()}")
    print(f"Dimensions:   {len(vec)}")
    print(f"Vector norm:  {sum(v * v for v in vec) ** 0.5:.6f}")
