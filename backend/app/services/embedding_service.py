import hashlib

import httpx
import numpy as np

from app.core.config import get_settings

settings = get_settings()


class EmbeddingService:
    def __init__(self, dim: int | None = None):
        self.dim = dim or settings.embedding_dimension
        self.provider = settings.embedding_provider

    def embed(self, text: str) -> list[float]:
        if self._should_use_openai():
            try:
                return self._embed_openai(text)
            except Exception:
                # Fallback for reliability if network/provider is not reachable.
                pass
        return self._embed_local(text)

    def _should_use_openai(self) -> bool:
        if self.provider == 'local':
            return False
        return bool(settings.openai_api_key)

    def _embed_openai(self, text: str) -> list[float]:
        payload = {
            'model': settings.embedding_model,
            'input': text[:16000],
            'dimensions': self.dim,
        }
        headers = {
            'Authorization': f'Bearer {settings.openai_api_key}',
            'Content-Type': 'application/json',
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post('https://api.openai.com/v1/embeddings', json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        vector = data['data'][0]['embedding']
        if len(vector) != self.dim:
            raise ValueError(f'Embedding dimension mismatch: expected {self.dim}, got {len(vector)}')
        return vector

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
