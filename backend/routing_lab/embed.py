"""Embed every SPROUT prompt once, locally and for free, and cache the vectors.

CPU-only this runs at roughly 15-20 prompts/s, so the full set takes under an hour; progress is
saved in chunks and a re-run resumes where it stopped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from routing_lab.download import COMPACT, OUT_DIR

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L12-v2"  # the RouterBench baseline encoder
CHUNK = 2000


def embeddings_path(model_name: str) -> Path:
    return OUT_DIR / f"embeddings_{model_name.split('/')[-1]}.npy"


def embed(model_name: str = DEFAULT_MODEL, max_seq_length: int = 128) -> Path:
    from sentence_transformers import SentenceTransformer

    out = embeddings_path(model_name)
    prompts = pd.read_parquet(COMPACT, columns=["prompt"])["prompt"].tolist()
    model = SentenceTransformer(model_name, device="cpu")
    model.max_seq_length = max_seq_length
    parts_dir = OUT_DIR / f"parts_{out.stem}"
    parts_dir.mkdir(exist_ok=True)
    parts = []
    for start in range(0, len(prompts), CHUNK):
        part = parts_dir / f"{start:06d}.npy"
        if not part.exists():
            vectors = model.encode(prompts[start : start + CHUNK], batch_size=32, normalize_embeddings=True)
            np.save(part, vectors.astype(np.float32))
        parts.append(part)
        print(f"{min(start + CHUNK, len(prompts))}/{len(prompts)}", flush=True)
    vectors = np.concatenate([np.load(p) for p in parts])
    np.save(out, vectors)
    print(f"{vectors.shape} -> {out}")
    return out


if __name__ == "__main__":
    embed(*sys.argv[1:2])
