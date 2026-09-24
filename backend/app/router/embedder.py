"""Prompt encoders for the learned router.

`SentenceTransformerEmbedder` is the real one (needs requirements-ml.txt). `HashingEmbedder` is a
dependency-free bag-of-words fallback (EMBEDDING_MODEL=hashing) used by the tests and by
deployments that cannot ship PyTorch; it is far cruder, so expect weaker routing from it.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from typing import Protocol

import numpy as np

from app.config.settings import get_settings

DIM = 384


class Embedder(Protocol):
    def embed(self, text: str) -> np.ndarray:
        """Unit-length float32 vector."""


class HashingEmbedder:
    name = "hashing"

    def embed(self, text: str) -> np.ndarray:
        vector = np.zeros(DIM, dtype=np.float32)
        words = re.findall(r"\w+", text.lower())
        for token in words + [f"{a} {b}" for a, b in zip(words, words[1:])]:
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            slot = int.from_bytes(digest[:4], "little") % DIM
            vector[slot] += 1.0 if digest[4] & 1 else -1.0
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm else vector


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, max_seq_length: int = 128) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self._model = SentenceTransformer(model_name, device="cpu")
        self._model.max_seq_length = max_seq_length

    def embed(self, text: str) -> np.ndarray:
        return self._model.encode(text, normalize_embeddings=True).astype(np.float32)


_embedder: Embedder | None = None
_embedder_name: str | None = None
_lock = threading.Lock()
_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
_CACHE_SIZE = 256


def get_embedder() -> Embedder:
    global _embedder, _embedder_name
    name = get_settings().embedding_model
    with _lock:
        if _embedder is None or _embedder_name != name:
            _embedder = HashingEmbedder() if name == "hashing" else SentenceTransformerEmbedder(name)
            _embedder_name = name
            _cache.clear()
        return _embedder


def embed_prompt(prompt: str) -> np.ndarray:
    """Embed a prompt, remembering the last few so routing and outcome recording share one encode."""
    key = hashlib.blake2b(prompt.encode(), digest_size=16).hexdigest()
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    vector = get_embedder().embed(prompt)
    with _lock:
        _cache[key] = vector
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return vector


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
