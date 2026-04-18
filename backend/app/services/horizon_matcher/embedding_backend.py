"""
embedding_backend.py — astrazione per embeddings locali/remoti.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def _resolve_cached_snapshot_path(model_name: str, cache_dir: str | None) -> str | None:
    if not cache_dir:
        return None

    repo_candidates = [model_name]
    if "/" not in model_name:
        repo_candidates.insert(0, f"sentence-transformers/{model_name}")

    for repo in repo_candidates:
        model_root = Path(cache_dir) / f"models--{repo.replace('/', '--')}"
        refs_main = model_root / "refs" / "main"
        snapshots_root = model_root / "snapshots"

        if refs_main.exists():
            revision = refs_main.read_text(encoding="utf-8").strip()
            snapshot = snapshots_root / revision
            if snapshot.is_dir():
                return str(snapshot)

        if snapshots_root.is_dir():
            candidates = sorted(p for p in snapshots_root.iterdir() if p.is_dir())
            if candidates:
                return str(candidates[-1])

    return None


class EmbeddingBackend:
    def __init__(self, config: dict[str, Any]):
        self.provider = str(config.get("embedding_provider", "sentence_transformers")).strip().lower()
        self.model = str(config.get("embedding_model", "all-MiniLM-L6-v2")).strip()
        self.fallback_model = str(config.get("embedding_fallback_model", "qwen3-embedding:4b")).strip()
        self.cache_dir = config.get("model_cache_dir")
        self.base_url = str(
            config.get("embedding_base_url")
            or os.getenv("OLLAMA_HOST")
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        self.timeout = int(config.get("embedding_timeout", 120))
        self.batch_size = max(1, int(config.get("embedding_batch_size", 16)))
        self._model: SentenceTransformer | None = None
        self._client: httpx.Client | None = None

    def _ensure_sentence_transformer(self) -> SentenceTransformer:
        if self._model is not None:
            return self._model

        local_snapshot = _resolve_cached_snapshot_path(self.model, self.cache_dir)
        if local_snapshot:
            logger.info("Caricamento modello embeddings da cache locale: %s", local_snapshot)
            self._model = SentenceTransformer(local_snapshot)
            return self._model

        logger.info("Modello embeddings %s non in cache locale: tentativo download.", self.model)
        self._model = SentenceTransformer(self.model, cache_folder=self.cache_dir)
        return self._model

    def _ensure_ollama_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if self.provider == "ollama":
            return self._embed_with_ollama(texts)
        return self._embed_with_sentence_transformers(texts)

    def embed_text(self, text: str) -> np.ndarray:
        vectors = self.embed_texts([text])
        return vectors[:1]

    def _embed_with_sentence_transformers(self, texts: list[str]) -> np.ndarray:
        model = self._ensure_sentence_transformer()
        return model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)

    def _embed_with_ollama_once(self, client: httpx.Client, model: str, texts: list[str]) -> np.ndarray:
        resp = client.post("/api/embed", json={"model": model, "input": texts})
        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise RuntimeError("Risposta embeddings vuota da Ollama")
        return np.asarray(embeddings, dtype=np.float32)

    def _embed_with_ollama(self, texts: list[str]) -> np.ndarray:
        client = self._ensure_ollama_client()
        all_vectors: list[np.ndarray] = []
        total = len(texts)

        for start in range(0, total, self.batch_size):
            chunk = texts[start : start + self.batch_size]
            end = start + len(chunk)
            try:
                vectors = self._embed_with_ollama_once(client, self.model, chunk)
            except Exception as exc:
                message = str(exc).lower()
                if (
                    self.fallback_model
                    and self.fallback_model != self.model
                    and ("does not support embeddings" in message or "400" in message)
                ):
                    logger.warning(
                        "Modello %s non compatibile con embeddings, fallback a %s (chunk %d-%d/%d)",
                        self.model,
                        self.fallback_model,
                        start + 1,
                        end,
                        total,
                    )
                    try:
                        vectors = self._embed_with_ollama_once(client, self.fallback_model, chunk)
                    except Exception as fb_exc:
                        raise RuntimeError(
                            f"Errore embeddings Ollama fallback ({self.fallback_model}) su chunk {start + 1}-{end}: {fb_exc}"
                        ) from fb_exc
                else:
                    raise RuntimeError(
                        f"Errore embeddings Ollama ({self.model}) su chunk {start + 1}-{end}: {exc}"
                    ) from exc

            all_vectors.append(vectors)
            logger.info("Embedding chunk completato %d-%d/%d", start + 1, end, total)

        if not all_vectors:
            raise RuntimeError("Nessun embedding calcolato")
        return np.vstack(all_vectors).astype(np.float32)
