"""
scorer.py — Step 3: algoritmo di fit ibrido pesato

Implementa calculate_reliability_fit(), che combina:
  Componente A (50%): similarità semantica via FAISS + sentence-transformers
  Componente B (30%): BM25 keyword match con boost per termini tecnici UE
  Componente C (20%): vincoli tecnici (TRL delta) + bonus eligibility

Ogni punteggio è auditabile: il dizionario score_breakdown conserva
tutti i valori intermedi e i pesi usati nel calcolo.
"""

import logging
import os
from typing import Optional
from pathlib import Path

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sentence_transformers import SentenceTransformer

from .config import get_matcher_config

logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()


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


def _load_embedding_model(model_name: str, cache_dir: str | None = None) -> SentenceTransformer:
    """
    Carica il modello di scoring preferendo uno snapshot locale già scaricato.
    """
    local_snapshot = _resolve_cached_snapshot_path(model_name, cache_dir)
    if local_snapshot:
        return SentenceTransformer(local_snapshot)

    logger.info("Modello %s non presente in cache locale: tentativo download.", model_name)
    return SentenceTransformer(model_name, cache_folder=cache_dir)


# ─── Componente A — Similarità Semantica ─────────────────────────────────────

def _embed_query(model: SentenceTransformer, text: str) -> np.ndarray:
    """
    Genera e normalizza L2 l'embedding di un testo query.

    Args:
        model: modello SentenceTransformer già caricato
        text: testo da embeddare

    Returns:
        Vettore float32 normalizzato, shape (1, dim)
    """
    vec = model.encode(
        [text],
        convert_to_numpy=True,
        show_progress_bar=False,
    ).astype(np.float32)
    faiss.normalize_L2(vec)
    return vec


def _cosine_to_01(sim: float) -> float:
    """
    Normalizza cosine similarity da [-1, 1] a [0, 1].

    Args:
        sim: valore cosine similarity in [-1, 1]

    Returns:
        Valore normalizzato in [0, 1]
    """
    return (sim + 1.0) / 2.0


def _compute_semantic_scores(
    company_profile: dict,
    calls: list[dict],
    faiss_index: faiss.Index,
    metadata: dict[int, str],
    model: SentenceTransformer,
) -> dict[str, tuple[float, float]]:
    """
    Componente A — Similarità Semantica.

    Calcola impact_match (A1) e technical_match (A2) per tutte le call
    tramite ricerca FAISS. Il layout dell'indice è:
      slot 2i   = outcomes della call i
      slot 2i+1 = scope della call i

    Args:
        company_profile: profilo aziendale
        calls: lista call da calls.json
        faiss_index: indice FAISS già caricato
        metadata: mapping int(faiss_slot) → call_id
        model: modello SentenceTransformer

    Returns:
        Dict {call_id: (impact_match, technical_match)} in [0,1]
    """
    # Mappa call_id → indice posizione nel corpus (per trovare slot FAISS)
    id_to_idx = {call["id"]: i for i, call in enumerate(calls)}

    # A1: embed mission → cerca nei vettori outcomes (slot pari)
    vec_mission = _embed_query(model, company_profile.get("mission", ""))
    # A2: embed technical_knowhow → cerca nei vettori scope (slot dispari)
    vec_tech = _embed_query(model, company_profile.get("technical_knowhow", ""))

    n_total = faiss_index.ntotal
    results: dict[str, tuple[float, float]] = {}

    for call in calls:
        cid = call["id"]
        idx = id_to_idx.get(cid)
        if idx is None:
            logger.warning("Call %s non trovata nel metadata, salto.", cid)
            results[cid] = (0.5, 0.5)
            continue

        slot_outcomes = idx * 2
        slot_scope = idx * 2 + 1

        if slot_outcomes >= n_total or slot_scope >= n_total:
            logger.warning(
                "Call %s: slot FAISS %d/%d fuori range (%d totali). "
                "Rigenera l'indice con python embedder.py.",
                cid, slot_outcomes, slot_scope, n_total,
            )
            results[cid] = (0.5, 0.5)
            continue

        # Estrae i vettori direttamente dall'indice
        vec_outcomes = faiss_index.reconstruct(slot_outcomes).reshape(1, -1).astype(np.float32)
        vec_scope = faiss_index.reconstruct(slot_scope).reshape(1, -1).astype(np.float32)

        # Prodotto interno = cosine similarity (vettori già normalizzati L2)
        impact_sim = float(np.dot(vec_mission, vec_outcomes.T).squeeze())
        tech_sim = float(np.dot(vec_tech, vec_scope.T).squeeze())

        impact_match = _cosine_to_01(impact_sim)
        technical_match = _cosine_to_01(tech_sim)

        logger.debug(
            "Call %s | impact_sim=%.4f → %.4f | tech_sim=%.4f → %.4f",
            cid, impact_sim, impact_match, tech_sim, technical_match,
        )
        results[cid] = (impact_match, technical_match)

    return results


# ─── Componente B — BM25 Keyword Match ───────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """
    Tokenizza un testo in parole lowercase senza punteggiatura.

    Args:
        text: testo da tokenizzare

    Returns:
        Lista di token
    """
    import re
    return re.findall(r"\b\w+\b", text.lower())


def _compute_bm25_scores(
    company_profile: dict,
    calls: list[dict],
    boost_factor: float,
    boost_terms: list[str],
) -> dict[str, tuple[float, bool]]:
    """
    Componente B — BM25 Keyword Match con boost per termini tecnici UE.

    Costruisce il corpus BM25 concatenando scope + expected_outcomes per
    ogni call. La query è description + keywords. Applica un moltiplicatore
    boost_factor alle call che condividono termini tecnici UE con la query.

    Args:
        company_profile: profilo aziendale
        calls: lista call da calls.json
        boost_factor: moltiplicatore boost (es. 1.15)
        boost_terms: lista di termini tecnici UE per il boost

    Returns:
        Dict {call_id: (bm25_score_normalizzato, boost_applied)} in [0,1]
    """
    # Costruzione corpus
    corpus_texts = [
        (call.get("scope") or "") + " " + (call.get("expected_outcomes") or "")
        for call in calls
    ]
    tokenized_corpus = [_tokenize(t) for t in corpus_texts]

    # Query
    query_text = (
        company_profile.get("description", "")
        + " "
        + " ".join(company_profile.get("keywords", []))
    )
    query_tokens = _tokenize(query_text)
    query_lower = query_text.lower()

    # Costruzione BM25
    try:
        bm25 = BM25Okapi(tokenized_corpus)
    except Exception as exc:
        logger.error("Errore costruzione BM25: %s", exc)
        return {call["id"]: (0.0, False) for call in calls}

    raw_scores = bm25.get_scores(query_tokens)

    # Identifica quali boost_terms sono presenti nella query
    active_boost_terms = [term for term in boost_terms if term in query_lower]
    logger.debug("Termini boost attivi nella query: %s", active_boost_terms)

    # Applica boost alle call che contengono i boost_terms attivi nel loro testo
    boosted_scores = np.array(raw_scores, dtype=float)
    boost_flags = []
    for i, (call, corpus_text) in enumerate(zip(calls, corpus_texts)):
        corpus_lower = corpus_text.lower()
        has_boost = any(term in corpus_lower for term in active_boost_terms)
        if has_boost:
            boosted_scores[i] *= boost_factor
            logger.debug("Boost applicato a %s (×%.2f)", call["id"], boost_factor)
        boost_flags.append(has_boost)

    # Min-max normalization
    max_score = boosted_scores.max()
    if max_score > 0:
        normalized = boosted_scores / max_score
    else:
        normalized = boosted_scores  # tutti zero

    results = {}
    for i, call in enumerate(calls):
        results[call["id"]] = (float(normalized[i]), boost_flags[i])
        logger.debug("BM25 %s: raw=%.4f boost=%s norm=%.4f",
                     call["id"], raw_scores[i], boost_flags[i], normalized[i])

    return results


# ─── Componente C — Vincoli Tecnici e Normativi ───────────────────────────────

def _compute_trl_score(trl_required: Optional[int], trl_current: int) -> float:
    """
    Componente C1 — TRL Delta Score.

    Calcola il punteggio di allineamento TRL in base alla differenza tra
    il TRL richiesto dalla call e quello attuale dell'azienda.

    Args:
        trl_required: TRL numerico richiesto dalla call (None = non specificato)
        trl_current: TRL attuale dell'azienda

    Returns:
        trl_score in [0, 1]
    """
    if trl_required is None:
        logger.debug("TRL non specificato → score neutro 0.6")
        return 0.6

    delta = trl_required - trl_current
    if delta <= 0:
        score = 1.0
    elif delta == 1:
        score = 0.75
    elif delta == 2:
        score = 0.5
    elif delta == 3:
        score = 0.25
    else:
        score = 0.0

    logger.debug("TRL delta=%d (req=%d, current=%d) → score=%.2f",
                 delta, trl_required, trl_current, score)
    return score


def _compute_eligibility_score(company_profile: dict, call: dict) -> float:
    """
    Componente C2 — Eligibility Bonuses.

    Assegna un bonus per ogni corrispondenza tra caratteristiche dell'azienda
    e condizioni specifiche della call, normalizzato su 5 bonus possibili.

    Args:
        company_profile: profilo aziendale
        call: dict della call da calls.json

    Returns:
        eligibility_score in [0, 1]
    """
    conditions = call.get("specific_conditions", {})
    bonuses = 0

    if company_profile.get("is_sme") and conditions.get("sme_eligible"):
        bonuses += 1
        logger.debug("  +1 bonus: SME eligible")
    if company_profile.get("ssh_capacity") and conditions.get("ssh_required"):
        bonuses += 1
        logger.debug("  +1 bonus: SSH capacity")
    if company_profile.get("fair_compliant") and conditions.get("fair_data"):
        bonuses += 1
        logger.debug("  +1 bonus: FAIR compliant")
    if company_profile.get("gender_dimension_active") and conditions.get("gender_dimension"):
        bonuses += 1
        logger.debug("  +1 bonus: Gender dimension")
    if call.get("cluster") in company_profile.get("clusters_interest", []):
        bonuses += 1
        logger.debug("  +1 bonus: cluster match (%s)", call.get("cluster"))

    score = bonuses / 5.0
    logger.debug("Eligibility bonuses=%d → score=%.2f", bonuses, score)
    return score


def _compute_constraints_score(
    company_profile: dict, call: dict
) -> tuple[float, float, float]:
    """
    Componente C — Vincoli Tecnici e Normativi.

    Combina TRL delta (60%) e eligibility bonuses (40%).

    Args:
        company_profile: profilo aziendale
        call: dict della call

    Returns:
        (constraints_score, trl_score, eligibility_score)
    """
    trl_score = _compute_trl_score(
        call.get("trl_required"), company_profile.get("trl_current", 5)
    )
    eligibility_score = _compute_eligibility_score(company_profile, call)
    constraints_score = 0.6 * trl_score + 0.4 * eligibility_score
    return constraints_score, trl_score, eligibility_score


# ─── Spider Axes ─────────────────────────────────────────────────────────────

def _compute_spider_axes(
    company_profile: dict,
    call: dict,
    impact_match: float,
    technical_match: float,
    trl_score: float,
    eligibility_score: float,
) -> dict[str, float]:
    """
    Calcola i 6 assi del radar chart scalati da 1 a 5.

    La scala lineare è: 1 + score_[0,1] * 4

    Args:
        company_profile: profilo aziendale
        call: dict della call
        impact_match: score A1 in [0,1]
        technical_match: score A2 in [0,1]
        trl_score: score C1 in [0,1]
        eligibility_score: score C2 in [0,1]

    Returns:
        Dict con 6 chiavi, valori in [1, 5]
    """
    conditions = call.get("specific_conditions", {})

    def to_15(v: float) -> float:
        return round(1.0 + v * 4.0, 4)

    # fair_compliance: 1.0 se entrambi, 0.5 se solo uno, 0.0 se nessuno
    fair_both = company_profile.get("fair_compliant") and conditions.get("fair_data")
    fair_one = company_profile.get("fair_compliant") or conditions.get("fair_data")
    fair_raw = 1.0 if fair_both else (0.5 if fair_one else 0.0)

    # inclusion_ethics: media di ssh e gender, pesata con i requisiti della call
    ssh_score = float(company_profile.get("ssh_capacity", False))
    gender_score = float(company_profile.get("gender_dimension_active", False))
    ssh_req = float(conditions.get("ssh_required", False))
    gender_req = float(conditions.get("gender_dimension", False))

    # Se la call non richiede né SSH né gender, usa la capacità interna come base
    if ssh_req + gender_req > 0:
        inclusion_raw = (ssh_score * (1 + ssh_req) + gender_score * (1 + gender_req)) / (
            2 + ssh_req + gender_req
        )
    else:
        inclusion_raw = (ssh_score + gender_score) / 2.0

    return {
        "trl_alignment": to_15(trl_score),
        "impact_policy": to_15(impact_match),
        "scope_methodology": to_15(technical_match),
        "consortium_stakeholders": to_15(eligibility_score),
        "fair_compliance": to_15(fair_raw),
        "inclusion_ethics": to_15(inclusion_raw),
    }


# ─── Main function ───────────────────────────────────────────────────────────

def calculate_reliability_fit(
    company_profile: dict,
    calls: list[dict],
    faiss_index: faiss.Index,
    metadata: dict[int, str],
    config: dict,
) -> list[dict]:
    """
    Calcola il Reliability Score per ogni call rispetto al profilo aziendale.

    Combina tre componenti pesate:
      A (default 50%): similarità semantica mission/outcomes + tech/scope
      B (default 30%): BM25 keyword match con boost per termini tecnici UE
      C (default 20%): TRL delta + eligibility bonuses

    Ogni risultato include score_breakdown auditabile con tutti i valori
    intermedi e i pesi effettivamente usati nel calcolo.

    Args:
        company_profile: dict con descrizione, TRL, cluster, flag, keywords
        calls: lista di dict da calls.json
        faiss_index: indice FAISS caricato con load_index()
        metadata: mapping int(faiss_slot) → call_id
        config: dict di configurazione (da CONFIG in config.py)

    Returns:
        Lista di dict ordinata per reliability_score decrescente, ciascuno con:
        call_id, title, cluster, type_of_action, reliability_score,
        score_breakdown, spider_axes, call_data
    """
    w_semantic = config.get("weight_semantic", 0.50)
    w_bm25 = config.get("weight_bm25", 0.30)
    w_constraints = config.get("weight_constraints", 0.20)

    logger.info(
        "Avvio scoring: %d call | pesi S=%.2f B=%.2f C=%.2f",
        len(calls), w_semantic, w_bm25, w_constraints,
    )

    # ── Caricamento modello ──────────────────────────────────────────────────
    model_name = config.get("embedding_model", "all-MiniLM-L6-v2")
    cache_dir = config.get("model_cache_dir")
    try:
        model = _load_embedding_model(model_name, cache_dir=cache_dir)
    except Exception as exc:
        raise RuntimeError(
            f"Impossibile caricare il modello '{model_name}': {exc}"
        ) from exc

    # ── Componente A ─────────────────────────────────────────────────────────
    logger.info("Componente A: calcolo similarità semantica...")
    semantic_scores = _compute_semantic_scores(
        company_profile, calls, faiss_index, metadata, model
    )

    # ── Componente B ─────────────────────────────────────────────────────────
    logger.info("Componente B: calcolo BM25...")
    bm25_scores = _compute_bm25_scores(
        company_profile,
        calls,
        config.get("bm25_boost_factor", 1.15),
        config.get("bm25_boost_terms", []),
    )

    # ── Componente C + score finale ──────────────────────────────────────────
    logger.info("Componente C + score finale...")
    results: list[dict] = []

    for call in calls:
        cid = call["id"]

        impact_match, technical_match = semantic_scores.get(cid, (0.5, 0.5))
        semantic_avg = (impact_match + technical_match) / 2.0

        bm25_score, bm25_boost_applied = bm25_scores.get(cid, (0.0, False))

        constraints_score, trl_score, eligibility_score = _compute_constraints_score(
            company_profile, call
        )

        reliability_score = (
            w_semantic * semantic_avg
            + w_bm25 * bm25_score
            + w_constraints * constraints_score
        )
        reliability_score = round(min(max(reliability_score, 0.0), 1.0), 4)

        semantic_contribution = w_semantic * semantic_avg
        bm25_contribution = w_bm25 * bm25_score
        constraints_contribution = w_constraints * constraints_score

        spider_axes = _compute_spider_axes(
            company_profile, call,
            impact_match, technical_match,
            trl_score, eligibility_score,
        )

        logger.debug(
            "Call %s | S=%.4f B=%.4f C=%.4f → R=%.4f",
            cid, semantic_avg, bm25_score, constraints_score, reliability_score,
        )

        results.append({
            "call_id": cid,
            "title": call.get("title", ""),
            "cluster": call.get("cluster", ""),
            "type_of_action": call.get("type_of_action", ""),
            "reliability_score": reliability_score,
            "score_breakdown": {
                "impact_match": round(impact_match, 4),
                "technical_match": round(technical_match, 4),
                "semantic_score": round(semantic_avg, 4),
                "bm25_score": round(bm25_score, 4),
                "bm25_boost_applied": bm25_boost_applied,
                "trl_score": round(trl_score, 4),
                "eligibility_score": round(eligibility_score, 4),
                "constraints_score": round(constraints_score, 4),
                "weighted_contributions": {
                    "semantic": round(semantic_contribution, 4),
                    "bm25": round(bm25_contribution, 4),
                    "constraints": round(constraints_contribution, 4),
                    "total": reliability_score,
                },
                "weights_used": {
                    "semantic": w_semantic,
                    "bm25": w_bm25,
                    "constraints": w_constraints,
                },
            },
            "spider_axes": spider_axes,
            "call_data": call,
        })

    results.sort(key=lambda x: x["reliability_score"], reverse=True)
    logger.info("Scoring completato. Top score: %.4f", results[0]["reliability_score"] if results else 0)

    return results
