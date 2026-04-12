from __future__ import annotations

import logging

import httpx
import numpy as np

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Lazy-loaded sentence-transformers model (loaded once on first use).
_st_model = None
_ST_MODEL_NAME = 'all-MiniLM-L6-v2'


def _get_st_model():
    global _st_model
    if _st_model is None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            _st_model = SentenceTransformer(_ST_MODEL_NAME)
            logger.info('sentence-transformers model loaded: %s', _ST_MODEL_NAME)
        except Exception as exc:
            logger.warning('sentence-transformers not available (%s); semantic matching will be degraded.', exc)
            _st_model = False  # Mark as unavailable so we don't retry every call.
    return _st_model if _st_model is not False else None


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
        model = _get_st_model()
        if model is not None:
            vec = model.encode(text[:8192], normalize_embeddings=True)
            vec = np.array(vec, dtype=np.float32)
            # Resize if model output dimension differs from configured dim.
            if len(vec) != self.dim:
                if len(vec) > self.dim:
                    vec = vec[:self.dim]
                else:
                    vec = np.pad(vec, (0, self.dim - len(vec)))
                norm = np.linalg.norm(vec) + 1e-8
                vec = vec / norm
            return vec.tolist()
        # Last-resort fallback: zero vector (will produce 0.5 cosine after normalization shift).
        # Warns clearly so the operator knows semantic matching is non-functional.
        logger.error(
            'No embedding provider available (no OpenAI key, sentence-transformers not installed). '
            'Install sentence-transformers: pip install sentence-transformers'
        )
        return [0.0] * self.dim

    @staticmethod
    def cosine(a: list[float], b: list[float]) -> float:
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        den = (np.linalg.norm(va) * np.linalg.norm(vb)) + 1e-8
        return float(np.dot(va, vb) / den)
