import hashlib

import numpy as np

from app.core.config import get_settings

settings = get_settings()


class EmbeddingService:
    def __init__(self, dim: int | None = None):
        self.dim = dim or settings.embedding_dimension

    def embed(self, text: str) -> list[float]:
        return self._embed_local(text)

    def _embed_local(self, text: str) -> list[float]:
        digest = hashlib.sha512(text.encode('utf-8')).digest()
        seed = int.from_bytes(digest[:8], 'big', signed=False)
        rng = np.random.default_rng(seed)
        vec = rng.normal(0, 1, self.dim).astype(np.float32)
        vec /= np.linalg.norm(vec) + 1e-8
        return vec.tolist()

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        den = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-8
        return float(np.dot(va, vb) / den)
