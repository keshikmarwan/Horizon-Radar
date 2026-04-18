"""
embedder.py — Step 2: calcolo embeddings → index.faiss + metadata.json

Carica calls.json, genera embeddings con sentence-transformers (all-MiniLM-L6-v2),
costruisce un indice FAISS IndexFlatIP su vettori L2-normalizzati e salva
il mapping faiss_index → call_id in metadata.json.
"""

import json
import logging
import os
import re
import sys
from typing import Optional

import faiss
import numpy as np

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from .config import get_matcher_config
from .embedding_backend import EmbeddingBackend

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()


def _prepare_embedding_text(value: str, max_chars: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]
# ─── Utility ─────────────────────────────────────────────────────────────────

def _index_is_fresh(config: dict | None = None) -> bool:
    """
    Controlla se l'indice FAISS è aggiornato rispetto a calls.json.

    Compara i timestamp di modifica: se index.faiss è più recente di
    calls.json, l'indice è considerato valido e non viene ricalcolato.

    Returns:
        True se l'indice esiste ed è aggiornato, False altrimenti
    """
    effective_config = config or CONFIG
    index_path = effective_config["faiss_index"]
    calls_path = effective_config["calls_json"]
    index_meta_path = effective_config.get("index_meta_json")

    if not os.path.exists(index_path):
        logger.debug("Index non trovato: %s", index_path)
        return False
    if not os.path.exists(calls_path):
        logger.debug("calls.json non trovato: %s", calls_path)
        return False
    if not index_meta_path or not os.path.exists(index_meta_path):
        logger.debug("index_meta.json non trovato: rebuild necessario")
        return False

    index_mtime = os.path.getmtime(index_path)
    calls_mtime = os.path.getmtime(calls_path)

    if index_mtime >= calls_mtime:
        try:
            with open(index_meta_path, "r", encoding="utf-8") as f:
                index_meta = json.load(f)
        except Exception:
            logger.debug("index_meta.json non leggibile: rebuild necessario")
            return False

        current_provider = effective_config.get("embedding_provider")
        current_model = effective_config.get("embedding_model")
        if (
            index_meta.get("embedding_provider") == current_provider
            and index_meta.get("embedding_model") == current_model
        ):
            logger.debug("Index aggiornato e coerente con provider/modello embeddings correnti")
            return True
        logger.debug("Provider/modello embeddings cambiati: rebuild necessario")
        return False

    logger.debug("calls.json più recente dell'index: ricalcolo necessario")
    return False


def _load_calls(calls_path: str) -> list[dict]:
    """
    Carica e valida calls.json.

    Args:
        calls_path: percorso al file calls.json

    Returns:
        Lista di dict delle call

    Raises:
        FileNotFoundError: se calls.json non esiste
        ValueError: se il file non è JSON valido
    """
    if not os.path.exists(calls_path):
        raise FileNotFoundError(
            f"calls.json non trovato: '{calls_path}'. "
            "Esegui prima: python ingest.py"
        )
    try:
        with open(calls_path, encoding="utf-8") as f:
            calls = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"calls.json non è JSON valido: {exc}") from exc

    logger.info("Caricate %d call da %s", len(calls), calls_path)
    return calls


# ─── Core ────────────────────────────────────────────────────────────────────

def build_index(calls_path: Optional[str] = None, config: dict | None = None) -> None:
    """
    Costruisce l'indice FAISS a partire da calls.json e lo salva su disco.

    Per ogni call genera due embeddings separati:
    - text_outcomes: basato su expected_outcomes (per impact match)
    - text_scope: basato su scope (per technical match)

    I vettori vengono normalizzati L2 prima dell'inserimento in FAISS
    IndexFlatIP, in modo che il prodotto interno equivalga alla cosine
    similarity. Il mapping posizione-indice → call_id viene salvato in
    metadata.json.

    Args:
        calls_path: percorso a calls.json. Default: CONFIG["calls_json"]

    Returns:
        None. Salva index.faiss e metadata.json su disco.
    """
    effective_config = config or CONFIG
    if calls_path is None:
        calls_path = effective_config["calls_json"]

    # ── Check cache ─────────────────────────────────────────────────────────
    if _index_is_fresh(config=effective_config):
        print("Index already up to date.")
        logger.info("Index FAISS già aggiornato, nessun ricalcolo necessario.")
        return

    calls = _load_calls(calls_path)

    # ── Caricamento modello ──────────────────────────────────────────────────
    model_name = effective_config["embedding_model"]
    embedding_provider = effective_config.get("embedding_provider", "sentence_transformers")
    logger.info("Caricamento embedding backend: provider=%s model=%s", embedding_provider, model_name)
    try:
        backend = EmbeddingBackend(effective_config)
    except Exception as exc:
        raise RuntimeError(
            f"Impossibile inizializzare il backend embeddings '{model_name}': {exc}\n"
            "Verifica la connessione internet al primo avvio."
        ) from exc

    # ── Preparazione testi ───────────────────────────────────────────────────
    # Indice FAISS layout: [outcomes_0, scope_0, outcomes_1, scope_1, ...]
    # Ogni call occupa 2 slot consecutivi: slot 2i = outcomes, slot 2i+1 = scope
    texts_outcomes: list[str] = []
    texts_scope: list[str] = []
    metadata: dict[int, str] = {}

    max_chars = int(effective_config.get("embedding_max_chars", 1800))

    for i, call in enumerate(calls):
        text_outcomes = _prepare_embedding_text(call.get("expected_outcomes") or "", max_chars=max_chars)
        text_scope = _prepare_embedding_text(call.get("scope") or "", max_chars=max_chars)

        texts_outcomes.append(text_outcomes)
        texts_scope.append(text_scope)

        # Mappa: slot FAISS → call_id
        metadata[i * 2] = call["id"]       # slot outcomes
        metadata[i * 2 + 1] = call["id"]   # slot scope
        logger.debug("Call %d: id=%s, outcomes=%d chars, scope=%d chars",
                     i, call["id"], len(text_outcomes), len(text_scope))

    # ── Encoding ─────────────────────────────────────────────────────────────
    logger.info("Encoding %d testi outcomes...", len(texts_outcomes))
    try:
        embeddings_outcomes = backend.embed_texts(texts_outcomes).astype(np.float32)

        logger.info("Encoding %d testi scope...", len(texts_scope))
        embeddings_scope = backend.embed_texts(texts_scope).astype(np.float32)
    except Exception as exc:
        raise RuntimeError(f"Errore durante l'encoding: {exc}") from exc

    # ── Interleave vettori: [o0, s0, o1, s1, ...] ───────────────────────────
    n = len(calls)
    dim = embeddings_outcomes.shape[1]
    all_vectors = np.empty((n * 2, dim), dtype=np.float32)
    all_vectors[0::2] = embeddings_outcomes  # slot pari = outcomes
    all_vectors[1::2] = embeddings_scope     # slot dispari = scope

    # ── Normalizzazione L2 ───────────────────────────────────────────────────
    faiss.normalize_L2(all_vectors)
    logger.info("Vettori normalizzati L2. Shape: %s", all_vectors.shape)

    # ── Costruzione indice FAISS ─────────────────────────────────────────────
    try:
        index = faiss.IndexFlatIP(dim)
        index.add(all_vectors)
        logger.info("Indice FAISS costruito: %d vettori, dim=%d", index.ntotal, dim)
    except Exception as exc:
        raise RuntimeError(f"Errore durante la costruzione dell'indice FAISS: {exc}") from exc

    # ── Salvataggio ──────────────────────────────────────────────────────────
    index_path = effective_config["faiss_index"]
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    try:
        faiss.write_index(index, index_path)
        logger.info("Indice salvato: %s", index_path)
    except Exception as exc:
        raise RuntimeError(f"Errore durante il salvataggio dell'indice FAISS: {exc}") from exc

    metadata_path = effective_config["metadata_json"]
    index_meta_path = effective_config["index_meta_json"]
    # Converti le chiavi in stringhe (JSON non supporta int keys)
    metadata_str_keys = {str(k): v for k, v in metadata.items()}
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata_str_keys, f, ensure_ascii=False, indent=2)
    logger.info("Metadata salvato: %s (%d entries)", metadata_path, len(metadata))

    with open(index_meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "embedding_provider": effective_config.get("embedding_provider"),
                "embedding_model": effective_config.get("embedding_model"),
                "vector_dim": int(dim),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info("Index meta salvato: %s", index_meta_path)

    print(f"\nIndice costruito con successo: {n} call, {n * 2} vettori totali.")
    print(f"  → {index_path}")
    print(f"  → {metadata_path}")


def load_index(config: dict | None = None) -> tuple[faiss.Index, dict[int, str]]:
    """
    Carica l'indice FAISS e i metadata da disco.

    Returns:
        (faiss_index, metadata_dict) dove metadata_dict mappa
        int(faiss_slot) → call_id

    Raises:
        FileNotFoundError: se index.faiss o metadata.json non esistono
    """
    effective_config = config or CONFIG
    index_path = effective_config["faiss_index"]
    metadata_path = effective_config["metadata_json"]

    if not os.path.exists(index_path):
        raise FileNotFoundError(
            f"Indice FAISS non trovato: '{index_path}'. "
            "Esegui prima: python embedder.py"
        )
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(
            f"Metadata non trovato: '{metadata_path}'. "
            "Esegui prima: python embedder.py"
        )

    try:
        index = faiss.read_index(index_path)
    except Exception as exc:
        raise RuntimeError(f"Errore durante il caricamento dell'indice FAISS: {exc}") from exc

    with open(metadata_path, encoding="utf-8") as f:
        raw = json.load(f)
    metadata = {int(k): v for k, v in raw.items()}

    logger.info("Indice caricato: %d vettori", index.ntotal)
    return index, metadata


# ─── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    calls_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG["calls_json"]
    build_index(calls_path, config=CONFIG)
