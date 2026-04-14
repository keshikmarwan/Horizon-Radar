"""
embedder.py — Step 2: calcolo embeddings → index.faiss + metadata.json

Carica calls.json, genera embeddings con sentence-transformers (all-MiniLM-L6-v2),
costruisce un indice FAISS IndexFlatIP su vettori L2-normalizzati e salva
il mapping faiss_index → call_id in metadata.json.
"""

import json
import logging
import os
import sys
from typing import Optional

import faiss
import numpy as np

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sentence_transformers import SentenceTransformer

from .config import get_matcher_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()


def _resolve_cached_snapshot_path(model_name: str, cache_dir: str | None) -> str | None:
    """
    Risolve il path locale dello snapshot HF se il modello è già in cache.
    """
    if not cache_dir:
        return None

    repo_candidates = [model_name]
    if "/" not in model_name:
        repo_candidates.insert(0, f"sentence-transformers/{model_name}")

    for repo in repo_candidates:
        safe_repo = repo.replace("/", "--")
        model_root = os.path.join(cache_dir, f"models--{safe_repo}")
        refs_main = os.path.join(model_root, "refs", "main")
        snapshots_root = os.path.join(model_root, "snapshots")

        if os.path.isfile(refs_main):
            with open(refs_main, "r", encoding="utf-8") as f:
                rev = f.read().strip()
            snapshot = os.path.join(snapshots_root, rev)
            if os.path.isdir(snapshot):
                return snapshot

        if os.path.isdir(snapshots_root):
            candidates = [
                os.path.join(snapshots_root, d)
                for d in os.listdir(snapshots_root)
                if os.path.isdir(os.path.join(snapshots_root, d))
            ]
            if candidates:
                return sorted(candidates)[-1]

    return None


def _load_embedding_model(model_name: str, cache_dir: str | None = None) -> SentenceTransformer:
    """
    Carica il modello embeddings usando prima il path snapshot locale.
    """
    local_snapshot = _resolve_cached_snapshot_path(model_name, cache_dir)
    if local_snapshot:
        logger.info("Caricamento modello da cache locale: %s", local_snapshot)
        return SentenceTransformer(local_snapshot)

    logger.info("Modello %s non trovato in cache locale: tentativo download.", model_name)
    return SentenceTransformer(model_name, cache_folder=cache_dir)


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

    if not os.path.exists(index_path):
        logger.debug("Index non trovato: %s", index_path)
        return False
    if not os.path.exists(calls_path):
        logger.debug("calls.json non trovato: %s", calls_path)
        return False

    index_mtime = os.path.getmtime(index_path)
    calls_mtime = os.path.getmtime(calls_path)

    if index_mtime >= calls_mtime:
        logger.debug("Index aggiornato (index_mtime=%f >= calls_mtime=%f)", index_mtime, calls_mtime)
        return True

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
    cache_dir = effective_config.get("model_cache_dir")
    logger.info("Caricamento modello: %s (download automatico al primo avvio)", model_name)
    try:
        model = _load_embedding_model(model_name, cache_dir=cache_dir)
    except Exception as exc:
        raise RuntimeError(
            f"Impossibile caricare il modello '{model_name}': {exc}\n"
            "Verifica la connessione internet al primo avvio."
        ) from exc

    # ── Preparazione testi ───────────────────────────────────────────────────
    # Indice FAISS layout: [outcomes_0, scope_0, outcomes_1, scope_1, ...]
    # Ogni call occupa 2 slot consecutivi: slot 2i = outcomes, slot 2i+1 = scope
    texts_outcomes: list[str] = []
    texts_scope: list[str] = []
    metadata: dict[int, str] = {}

    for i, call in enumerate(calls):
        text_outcomes = call.get("expected_outcomes") or ""
        text_scope = call.get("scope") or ""

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
        embeddings_outcomes = model.encode(
            texts_outcomes,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)

        logger.info("Encoding %d testi scope...", len(texts_scope))
        embeddings_scope = model.encode(
            texts_scope,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        ).astype(np.float32)
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
    # Converti le chiavi in stringhe (JSON non supporta int keys)
    metadata_str_keys = {str(k): v for k, v in metadata.items()}
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata_str_keys, f, ensure_ascii=False, indent=2)
    logger.info("Metadata salvato: %s (%d entries)", metadata_path, len(metadata))

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
