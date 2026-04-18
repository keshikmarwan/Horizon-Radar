"""
scorer.py — motore ibrido AHP + Gurobi LP per Horizon Fit Analyzer.

Il file mantiene i segnali legacy come feature extractor interno e delega
la decisione finale a un modello AHP + Linear Programming.
"""

import numpy as np
from scipy.linalg import eig
import gurobipy as gp
from gurobipy import GRB
import json


class AHPScorer:
    DEFAULT_PAIRWISE = np.array([
        [1,   3,   5,   2],
        [1/3, 1,   3,   1],
        [1/5, 1/3, 1,   0.5],
        [0.5, 1,   2,   1]
    ], dtype=float)

    def __init__(self, pairwise_matrix=None):
        self.matrix = pairwise_matrix if pairwise_matrix is not None else self.DEFAULT_PAIRWISE
        self.weights, self.lambda_max, self.ci, self.cr = self._calculate_ahp()

    def _calculate_ahp(self):
        eigenvalues, eigenvectors = eig(self.matrix)
        max_idx = np.argmax(np.real(eigenvalues))
        priority = np.real(eigenvectors[:, max_idx])
        priority = priority / np.sum(priority)
        lambda_max = np.real(eigenvalues[max_idx])
        n = self.matrix.shape[0]
        ci = (lambda_max - n) / (n - 1)
        ri_dict = {3: 0.58, 4: 0.90, 5: 1.12}
        ri = ri_dict.get(n, 1.49)
        cr = ci / ri if ri > 0 else 0
        return priority, lambda_max, ci, cr


class HybridAHPLPGurobiScorer:
    def __init__(self, pairwise_matrix=None):
        self.ahp = AHPScorer(pairwise_matrix)
        self.weights = self.ahp.weights

    def solve_lp(self, local_scores: dict, hard_constraints: dict) -> dict:
        model = gp.Model("Horizon_Fit_Optimization")
        model.setParam('OutputFlag', 0)

        x = {
            'excellence': model.addVar(lb=0, ub=local_scores['excellence'], name="x_excellence"),
            'impact': model.addVar(lb=0, ub=local_scores['impact'], name="x_impact"),
            'implementation': model.addVar(lb=0, ub=local_scores['implementation'], name="x_implementation"),
            'tech_fit': model.addVar(lb=0, ub=local_scores['tech_fit'], name="x_tech_fit")
        }

        model.setObjective(
            self.weights[0] * x['excellence'] +
            self.weights[1] * x['impact'] +
            self.weights[2] * x['implementation'] +
            self.weights[3] * x['tech_fit'],
            GRB.MAXIMIZE
        )

        if hard_constraints.get('trl_violation', False):
            model.addConstr(x['excellence'] <= 0.3, name="TRL_hard")
        if hard_constraints.get('budget_company_available', 0) < hard_constraints.get('budget_max', 999999999):
            model.addConstr(x['implementation'] <= 0.4, name="Budget_hard")
        if hard_constraints.get('sme_required', False) and not hard_constraints.get('sme_ok', False):
            model.addConstr(x['implementation'] <= 0.2, name="SME_hard")
        if hard_constraints.get('ssh_required', False):
            model.addConstr(x['impact'] <= 0.5, name="SSH_hard")
        if hard_constraints.get('gender_balance_required', False):
            model.addConstr(x['implementation'] <= 0.6, name="Gender_hard")

        model.optimize()

        if model.status == GRB.OPTIMAL:
            optimal_x = {k: float(v.X) for k, v in x.items()}
            fit_score = float(model.ObjVal)
            status_str = "Optimal"
        else:
            optimal_x = {k: 0.0 for k in x}
            fit_score = 0.0
            status_str = gp.GRB.statusDict.get(model.status, "Unknown")

        breakdown = {
            crit: round(self.weights[i] * optimal_x[crit], 4)
            for i, crit in enumerate(['excellence', 'impact', 'implementation', 'tech_fit'])
        }

        return {
            "fit_score": round(fit_score, 4),
            "fit_score_100": round(fit_score * 100, 2),
            "weights": {k: round(v, 4) for k, v in zip(['excellence','impact','implementation','tech_fit'], self.weights)},
            "breakdown": breakdown,
            "optimal_contributions": optimal_x,
            "status": status_str,
            "cr": round(self.ahp.cr, 4),
            "consistency_ok": self.ahp.cr < 0.1,
            "constraints_applied": hard_constraints,
            "solver": "Gurobi"
        }


import logging
import os
import re
from typing import Any, Optional

import faiss
from rank_bm25 import BM25Okapi

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from .config import get_matcher_config
from .embedding_backend import EmbeddingBackend

logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()
def _embed_query(backend: EmbeddingBackend, text: str) -> np.ndarray:
    vec = backend.embed_text(text).astype(np.float32)
    faiss.normalize_L2(vec)
    return vec


def _cosine_to_01(sim: float) -> float:
    return (sim + 1.0) / 2.0


def _compute_semantic_scores(
    company_profile: dict[str, Any],
    calls: list[dict[str, Any]],
    faiss_index: faiss.Index,
    metadata: dict[int, str],
    backend: EmbeddingBackend,
) -> dict[str, tuple[float, float]]:
    del metadata
    id_to_idx = {call["id"]: i for i, call in enumerate(calls)}
    vec_mission = _embed_query(backend, company_profile.get("mission", ""))
    vec_tech = _embed_query(backend, company_profile.get("technical_knowhow", ""))

    n_total = faiss_index.ntotal
    results: dict[str, tuple[float, float]] = {}

    for call in calls:
        cid = call["id"]
        idx = id_to_idx.get(cid)
        if idx is None:
            results[cid] = (0.5, 0.5)
            continue

        slot_outcomes = idx * 2
        slot_scope = idx * 2 + 1
        if slot_outcomes >= n_total or slot_scope >= n_total:
            results[cid] = (0.5, 0.5)
            continue

        vec_outcomes = faiss_index.reconstruct(slot_outcomes).reshape(1, -1).astype(np.float32)
        vec_scope = faiss_index.reconstruct(slot_scope).reshape(1, -1).astype(np.float32)
        impact_sim = float(np.dot(vec_mission, vec_outcomes.T).squeeze())
        tech_sim = float(np.dot(vec_tech, vec_scope.T).squeeze())
        results[cid] = (_cosine_to_01(impact_sim), _cosine_to_01(tech_sim))

    return results


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _compute_bm25_scores(
    company_profile: dict[str, Any],
    calls: list[dict[str, Any]],
    boost_factor: float,
    boost_terms: list[str],
) -> dict[str, tuple[float, bool]]:
    corpus_texts = [
        (call.get("scope") or "") + " " + (call.get("expected_outcomes") or "")
        for call in calls
    ]
    tokenized_corpus = [_tokenize(t) for t in corpus_texts]

    query_text = company_profile.get("description", "") + " " + " ".join(company_profile.get("keywords", []))
    query_tokens = _tokenize(query_text)
    query_lower = query_text.lower()

    try:
        bm25 = BM25Okapi(tokenized_corpus)
    except Exception:
        return {call["id"]: (0.0, False) for call in calls}

    raw_scores = bm25.get_scores(query_tokens)
    active_boost_terms = [term for term in boost_terms if term in query_lower]

    boosted_scores = np.array(raw_scores, dtype=float)
    boost_flags: list[bool] = []
    for i, corpus_text in enumerate(corpus_texts):
        corpus_lower = corpus_text.lower()
        has_boost = any(term in corpus_lower for term in active_boost_terms)
        if has_boost:
            boosted_scores[i] *= boost_factor
        boost_flags.append(has_boost)

    max_score = boosted_scores.max() if len(boosted_scores) else 0.0
    normalized = boosted_scores / max_score if max_score > 0 else boosted_scores

    return {
        call["id"]: (float(normalized[i]), boost_flags[i])
        for i, call in enumerate(calls)
    }


def _compute_trl_score(trl_required: Optional[int], trl_current: int) -> float:
    if trl_required is None:
        return 0.6

    delta = trl_required - trl_current
    if delta <= 0:
        return 1.0
    if delta == 1:
        return 0.75
    if delta == 2:
        return 0.5
    if delta == 3:
        return 0.25
    return 0.0


def _compute_eligibility_score(company_profile: dict[str, Any], call: dict[str, Any]) -> float:
    conditions = call.get("specific_conditions", {})
    bonuses = 0

    if company_profile.get("is_sme") and conditions.get("sme_eligible"):
        bonuses += 1
    if company_profile.get("ssh_capacity") and conditions.get("ssh_required"):
        bonuses += 1
    if company_profile.get("fair_compliant") and conditions.get("fair_data"):
        bonuses += 1
    if company_profile.get("gender_dimension_active") and conditions.get("gender_dimension"):
        bonuses += 1
    if call.get("cluster") in company_profile.get("clusters_interest", []):
        bonuses += 1

    return bonuses / 5.0


def _compute_constraints_score(
    company_profile: dict[str, Any],
    call: dict[str, Any],
) -> tuple[float, float, float]:
    trl_score = _compute_trl_score(call.get("trl_required"), company_profile.get("trl_current", 5))
    eligibility_score = _compute_eligibility_score(company_profile, call)
    constraints_score = 0.6 * trl_score + 0.4 * eligibility_score
    return constraints_score, trl_score, eligibility_score


def _compute_spider_axes(
    company_profile: dict[str, Any],
    call: dict[str, Any],
    impact_match: float,
    technical_match: float,
    trl_score: float,
    eligibility_score: float,
) -> dict[str, float]:
    conditions = call.get("specific_conditions", {})

    def to_15(v: float) -> float:
        return round(1.0 + v * 4.0, 4)

    fair_both = company_profile.get("fair_compliant") and conditions.get("fair_data")
    fair_one = company_profile.get("fair_compliant") or conditions.get("fair_data")
    fair_raw = 1.0 if fair_both else (0.5 if fair_one else 0.0)

    ssh_score = float(company_profile.get("ssh_capacity", False))
    gender_score = float(company_profile.get("gender_dimension_active", False))
    ssh_req = float(conditions.get("ssh_required", False))
    gender_req = float(conditions.get("gender_dimension", False))

    if ssh_req + gender_req > 0:
        inclusion_raw = (ssh_score * (1 + ssh_req) + gender_score * (1 + gender_req)) / (2 + ssh_req + gender_req)
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


def _parse_budget_value(raw_budget: Any) -> float:
    if raw_budget is None:
        return 999999999.0
    if isinstance(raw_budget, (int, float)):
        return float(raw_budget)

    text = str(raw_budget).strip().lower()
    if not text:
        return 999999999.0

    multiplier = 1.0
    if "billion" in text:
        multiplier = 1_000_000_000.0
    elif "million" in text or "m eur" in text or "meur" in text or "m€" in text:
        multiplier = 1_000_000.0

    cleaned = text.replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    if not match:
        digits = re.sub(r"[^\d]", "", text)
        return float(digits) if digits else 999999999.0
    return float(match.group(1)) * multiplier


def _build_local_scores(
    impact_match: float,
    technical_match: float,
    semantic_score: float,
    bm25_score: float,
    constraints_score: float,
) -> dict[str, float]:
    return {
        "excellence": round(impact_match, 4),
        "impact": round((semantic_score + bm25_score) / 2.0, 4),
        "implementation": round(constraints_score, 4),
        "tech_fit": round(technical_match, 4),
    }


def _build_hard_constraints(
    company_profile: dict[str, Any],
    call: dict[str, Any],
) -> dict[str, Any]:
    profile_budget_max = company_profile.get("budget_max")
    return {
        "trl_violation": call.get("trl_required") is not None and company_profile.get("trl_current", 5) < call.get("trl_required"),
        "budget_company_available": float(company_profile.get("budget_company_available", 0.0) or 0.0),
        "budget_max": float(profile_budget_max) if profile_budget_max not in (None, "") else _parse_budget_value(call.get("budget_indicative")),
        "sme_required": bool((call.get("specific_conditions") or {}).get("sme_eligible")),
        "sme_ok": bool(company_profile.get("is_sme", False)),
        "ssh_required": bool((call.get("specific_conditions") or {}).get("ssh_required")),
        "gender_balance_required": bool(company_profile.get("gender_balance_required", False)),
    }


def _solve_hybrid_score(
    hybrid_scorer: HybridAHPLPGurobiScorer,
    local_scores: dict[str, float],
    hard_constraints: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = hybrid_scorer.solve_lp(local_scores=local_scores, hard_constraints=hard_constraints)
    except Exception as exc:
        raise RuntimeError(
            "Il motore di scoring richiede Gurobi operativo e una licenza valida."
        ) from exc

    if result.get("status") != "Optimal":
        raise RuntimeError(
            f"Il motore Gurobi non ha prodotto una soluzione ottimale ({result.get('status', 'Unknown')})."
        )

    result["local_scores"] = {k: round(float(v), 4) for k, v in local_scores.items()}
    return result


def calculate_reliability_fit(
    company_profile: dict[str, Any],
    calls: list[dict[str, Any]],
    faiss_index: faiss.Index,
    metadata: dict[int, str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    backend = EmbeddingBackend(config)

    semantic_scores = _compute_semantic_scores(company_profile, calls, faiss_index, metadata, backend)
    bm25_scores = _compute_bm25_scores(
        company_profile,
        calls,
        config.get("bm25_boost_factor", 1.15),
        config.get("bm25_boost_terms", []),
    )
    hybrid_scorer = HybridAHPLPGurobiScorer()

    results: list[dict[str, Any]] = []
    for call in calls:
        cid = call["id"]
        impact_match, technical_match = semantic_scores.get(cid, (0.5, 0.5))
        semantic_score = (impact_match + technical_match) / 2.0
        bm25_score, _bm25_boost_applied = bm25_scores.get(cid, (0.0, False))
        constraints_score, trl_score, eligibility_score = _compute_constraints_score(company_profile, call)
        local_scores = _build_local_scores(
            impact_match=impact_match,
            technical_match=technical_match,
            semantic_score=semantic_score,
            bm25_score=bm25_score,
            constraints_score=constraints_score,
        )
        hard_constraints = _build_hard_constraints(company_profile, call)
        score_breakdown = _solve_hybrid_score(
            hybrid_scorer=hybrid_scorer,
            local_scores=local_scores,
            hard_constraints=hard_constraints,
        )
        spider_axes = _compute_spider_axes(
            company_profile,
            call,
            impact_match,
            technical_match,
            trl_score,
            eligibility_score,
        )

        results.append({
            "call_id": cid,
            "title": call.get("title", ""),
            "cluster": call.get("cluster", ""),
            "type_of_action": call.get("type_of_action", ""),
            "fit_score": score_breakdown["fit_score"],
            "fit_score_100": score_breakdown["fit_score_100"],
            "score_breakdown": score_breakdown,
            "spider_axes": spider_axes,
            "call_data": call,
        })

    results.sort(key=lambda x: x["fit_score"], reverse=True)
    logger.info("Scoring completato. Top fit score: %.4f", results[0]["fit_score"] if results else 0.0)
    return results
