import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from .config import get_matcher_config
from .embedder import load_index
from .explainer import generate_justification
from .scorer import calculate_reliability_fit


class HorizonMatcherError(Exception):
    pass


def _default_data_dir() -> Path:
    env = os.getenv("HORIZON_MATCHER_DATA_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parents[3] / "data" / "horizon_matcher").resolve()


class HorizonMatcherEngine:
    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or _default_data_dir()

    def _config(self) -> dict[str, Any]:
        return get_matcher_config(self.data_dir)

    def status(self) -> dict[str, Any]:
        config = self._config()
        return {
            "data_dir": str(self.data_dir),
            "calls_json": Path(config["calls_json"]).exists(),
            "index_faiss": Path(config["faiss_index"]).exists(),
            "metadata_json": Path(config["metadata_json"]).exists(),
            "audit_log": Path(config["audit_log"]).exists(),
        }

    def _ensure_dependencies(self) -> None:
        try:
            import faiss  # noqa: F401
            import rank_bm25  # noqa: F401
            import sentence_transformers  # noqa: F401
        except Exception as exc:
            raise HorizonMatcherError(
                "Dipendenze mancanti: installa `faiss-cpu`, `sentence-transformers`, `rank_bm25` nel backend."
            ) from exc

    def _load_calls(self, calls_json_path: str) -> list[dict[str, Any]]:
        path = Path(calls_json_path)
        if not path.exists():
            raise HorizonMatcherError(f"Asset matcher mancante: {path}")
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            raise HorizonMatcherError(f"Impossibile leggere {path}: {exc}") from exc
        if not isinstance(data, list):
            raise HorizonMatcherError("Formato calls.json non valido (attesa lista di call).")
        return data

    def score(self, profile: dict[str, Any], top_n: int = 10) -> dict[str, Any]:
        self._ensure_dependencies()
        config = self._config()

        calls = self._load_calls(config["calls_json"])

        try:
            faiss_index, metadata = load_index(config=config)
        except Exception as exc:
            raise HorizonMatcherError(str(exc)) from exc

        try:
            scored_calls = calculate_reliability_fit(
                company_profile=profile,
                calls=calls,
                faiss_index=faiss_index,
                metadata=metadata,
                config=config,
            )
        except Exception as exc:
            raise HorizonMatcherError(f"Errore nel calcolo matcher: {exc}") from exc

        def map_result(item: dict[str, Any], justification: str) -> dict[str, Any]:
            return {
                "call_id": item.get("call_id", ""),
                "title": item.get("title", ""),
                "cluster": item.get("cluster"),
                "type_of_action": item.get("type_of_action"),
                "reliability_score": item.get("reliability_score", 0.0),
                "score_breakdown": item.get("score_breakdown", {}),
                "spider_axes": item.get("spider_axes", {}),
                "justification": justification,
            }

        results = []
        for item in scored_calls[:top_n]:
            justification, _audit = generate_justification(item, profile, config=config)
            results.append(map_result(item, justification))

        other_results = []
        for item in scored_calls[top_n:]:
            justification, _audit = generate_justification(item, profile, config=config)
            other_results.append(map_result(item, justification))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "top_n": top_n,
            "total_calls": len(calls),
            "results": results,
            "other_results": other_results,
            "status": self.status(),
        }
