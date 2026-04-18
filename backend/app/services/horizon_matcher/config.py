"""
Config centralizzata per Horizon Europe Matcher.
"""

import os
from pathlib import Path


def _default_data_dir() -> Path:
    env = os.getenv("HORIZON_MATCHER_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parents[3] / "data" / "horizon_matcher").resolve()


def get_matcher_config(data_dir: str | Path | None = None) -> dict:
    base = Path(data_dir).expanduser().resolve() if data_dir else _default_data_dir()
    return {
        "weight_semantic": 0.50,
        "weight_bm25": 0.30,
        "weight_constraints": 0.20,
        "embedding_provider": os.getenv("EMBEDDING_PROVIDER", "ollama"),
        "embedding_model": os.getenv("EMBEDDING_MODEL", "qwen3-embedding:4b"),
        "embedding_fallback_model": os.getenv("EMBEDDING_FALLBACK_MODEL", "qwen3-embedding:4b"),
        "embedding_base_url": os.getenv("EMBEDDING_BASE_URL") or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"),
        "embedding_timeout": int(os.getenv("EMBEDDING_TIMEOUT", "300")),
        "embedding_batch_size": int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
        "embedding_max_chars": int(os.getenv("EMBEDDING_MAX_CHARS", "1800")),
        "model_cache_dir": str(base / "models"),
        "bm25_boost_factor": 1.15,
        "bm25_boost_terms": [
            "ai", "artificial intelligence", "machine learning",
            "digital twin", "virtual human twin", "vht",
            "post-quantum cryptography", "pqc", "cybersecurity", "quantum",
            "safe and sustainable by design", "ssbd", "circular economy",
            "green deal", "climate neutrality", "net zero",
            "health data space", "federated learning", "gdpr",
        ],
        "pdf_path": str(base / "work_programme.pdf"),
        "calls_json": str(base / "calls.json"),
        "faiss_index": str(base / "index.faiss"),
        "metadata_json": str(base / "metadata.json"),
        "index_meta_json": str(base / "index_meta.json"),
        "qa_report": str(base / "qa_report.json"),
        "audit_log": str(base / "audit_log.jsonl"),
        "top_n": 10,
        "clusters": [
            "Health", "Digital", "Climate", "Energy", "Mobility",
            "Food", "Space", "Security", "Culture", "Manufacturing",
        ],
        "toa_mapping": {
            "research and innovation action": "RIA",
            "innovation action": "IA",
            "coordination and support action": "CSA",
            "pre-commercial procurement": "PCP",
            "public procurement of innovative solutions": "PPI",
            "programme co-fund action": "COFUND",
        },
    }


CONFIG = get_matcher_config()
