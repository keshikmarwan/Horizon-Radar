"""
explainer.py — spiegazioni auditabili e founder-friendly per il motore AHP + Gurobi LP.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from .config import get_matcher_config
from .llm_explainer import generate_clear_explanation
from .llm_fit_assistant import generate_ai_fit_review

logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()

CRITERIA_KEYS = ["excellence", "impact", "implementation", "tech_fit"]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _dominant_component(score_breakdown: dict[str, Any]) -> tuple[str, float]:
    breakdown = score_breakdown.get("breakdown", {}) or {}
    if not breakdown:
        return "fit", 0.0
    dominant = max(breakdown, key=breakdown.get)
    return dominant, float(breakdown.get(dominant, 0.0))


def _estimate_caps(constraints: dict[str, Any]) -> list[str]:
    caps: list[str] = []

    if constraints.get("trl_violation", False):
        caps.append("Cap TRL su Excellence (x_excellence <= 0.3)")

    budget_available = _safe_float(constraints.get("budget_company_available"), 0.0)
    budget_max = _safe_float(constraints.get("budget_max"), 999999999.0)
    if budget_available < budget_max:
        caps.append("Cap budget su Implementation (x_implementation <= 0.4)")

    if constraints.get("sme_required", False) and not constraints.get("sme_ok", False):
        caps.append("Cap SME su Implementation (x_implementation <= 0.2)")

    if constraints.get("ssh_required", False):
        caps.append("Cap SSH su Impact (x_impact <= 0.5)")

    if constraints.get("gender_balance_required", False):
        caps.append("Cap gender balance su Implementation (x_implementation <= 0.6)")

    return caps


def _extract_quotes(call_data: dict[str, Any], max_items: int = 3) -> list[str]:
    excerpts: list[str] = []
    for field in ("expected_outcomes", "scope"):
        text = str(call_data.get(field) or "").strip()
        if not text:
            continue
        lines = [ln.strip(" •\t-") for ln in text.splitlines() if ln.strip()]
        for ln in lines:
            if len(ln) >= 60:
                excerpts.append(ln[:280] + ("…" if len(ln) > 280 else ""))
            if len(excerpts) >= max_items:
                return excerpts
    return excerpts[:max_items]


def _build_gap_actions(score_breakdown: dict[str, Any], call_data: dict[str, Any]) -> tuple[list[str], list[str]]:
    local_scores = score_breakdown.get("local_scores", {}) or {}
    constraints = score_breakdown.get("constraints_applied", {}) or {}

    gaps: list[str] = []
    actions: list[str] = []

    if _safe_float(local_scores.get("excellence"), 0.0) < 0.55:
        gaps.append("Excellence sotto soglia competitiva: narrativa scientifica da rafforzare")
        actions.append("Definire proof plan tecnico con milestone TRL e metriche di validazione (90 giorni)")

    if _safe_float(local_scores.get("impact"), 0.0) < 0.55:
        gaps.append("Impact non ancora distintivo su outcomes e policy relevance")
        actions.append("Allineare proposition agli expected outcomes della call con KPI misurabili (60 giorni)")

    if _safe_float(local_scores.get("implementation"), 0.0) < 0.55:
        gaps.append("Implementation debole: piano esecutivo/consortium readiness non sufficiente")
        actions.append("Costruire shortlist partner (end-user, integrator, academia) e governance WP (90-120 giorni)")

    if constraints.get("trl_violation"):
        trl_req = call_data.get("trl_required")
        gaps.append(f"TRL aziendale inferiore al requisito della call (target: {trl_req})")
        actions.append("Eseguire pilot dimostrativo per salire di almeno 1 livello TRL (3-6 mesi)")

    if constraints.get("sme_required") and not constraints.get("sme_ok"):
        gaps.append("Requisito SME non soddisfatto dal profilo corrente")
        actions.append("Valutare ruolo da partner o struttura legale/cap table compatibile con requisiti SME")

    if constraints.get("ssh_required"):
        gaps.append("La call richiede copertura SSH esplicita")
        actions.append("Integrare partner SSH e work package dedicato a impatti sociali/adozione")

    if constraints.get("gender_balance_required"):
        gaps.append("Vincolo gender balance attivo sul piano di implementazione")
        actions.append("Formalizzare policy e target gender balance su team/proposal")

    if not gaps:
        gaps.append("Nessun gap bloccante evidente dai vincoli hard del solver")
    if not actions:
        actions.append("Consolidare la bozza di proposal con piano operativo e risk register")

    return gaps[:6], actions[:6]


class HorizonExplainer:
    """Genera spiegazione tecnica + narrativa business-friendly per una call."""

    def __init__(self, pairwise_matrix: list[list[float]] | None = None):
        if pairwise_matrix is None:
            pairwise_matrix = [
                [1, 3, 5, 2],
                [1 / 3, 1, 3, 1],
                [1 / 5, 1 / 3, 1, 0.5],
                [0.5, 1, 2, 1],
            ]
        self.pairwise_matrix = pairwise_matrix

    def generate_full_explanation(
        self,
        call: dict[str, Any],
        scores: dict[str, Any],
        profile: dict[str, Any],
        pdf_excerpts: list[str] | None = None,
    ) -> dict[str, Any]:
        breakdown = scores.get("score_breakdown", {}) or {}
        weights = breakdown.get("weights", {}) or {}
        local_scores = breakdown.get("local_scores", {}) or {}
        optimal = breakdown.get("optimal_contributions", {}) or {}
        constraints = breakdown.get("constraints_applied", {}) or {}
        dominant, dominant_val = _dominant_component(breakdown)
        caps = _estimate_caps(constraints)
        quotes = pdf_excerpts or _extract_quotes(call)
        gaps, actions = _build_gap_actions(breakdown, call)

        call_id = scores.get("call_id", "")
        fit_score_100 = _safe_float(scores.get("fit_score_100"), 0.0)
        solver_status = breakdown.get("status", "Unknown")
        cr = _safe_float(breakdown.get("cr"), 0.0)

        clear_text = (
            f"La call {call_id} ottiene un fit del {fit_score_100:.1f}% dopo ottimizzazione LP. "
            f"Il criterio dominante e' {dominant} (contributo {dominant_val * 100:.1f}/100). "
            f"Solver: {solver_status}, CR AHP: {cr:.4f}."
        )

        # LLM explainer (opzionale, con fallback automatico)
        llm_clear = generate_clear_explanation(call=call, scores=scores, profile=profile)
        ai_fit_review = generate_ai_fit_review(call=call, scores=scores, profile=profile)

        return {
            "ahp_detailed": {
                "pairwise_matrix": self.pairwise_matrix,
                "weights": {k: _safe_float(weights.get(k), 0.0) for k in CRITERIA_KEYS},
                "consistency": {
                    "lambda_max": None,
                    "ci": None,
                    "cr": cr,
                    "consistency_ok": bool(breakdown.get("consistency_ok", False)),
                },
                "local_scores_pre_lp": {k: _safe_float(local_scores.get(k), 0.0) for k in CRITERIA_KEYS},
                "optimal_post_lp": {k: _safe_float(optimal.get(k), 0.0) for k in CRITERIA_KEYS},
                "breakdown": {k: _safe_float((breakdown.get("breakdown", {}) or {}).get(k), 0.0) for k in CRITERIA_KEYS},
                "lp_constraints_effect": caps,
            },
            "clear_explanation": llm_clear or {
                "testo_semplice": clear_text,
                "citazioni_dirette": quotes[:3],
                "gap_principali": gaps,
                "azioni_concrete": actions,
                "criterio_dominante": dominant,
            },
            "ai_fit_review": ai_fit_review,
            "meta": {
                "call_id": call_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "profile_trl": profile.get("trl_current"),
            },
        }


def generate_justification(
    scored_call: dict[str, Any],
    company_profile: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Compat layer: ritorna anche spiegazione strutturata per UI/report."""
    score_breakdown = scored_call.get("score_breakdown", {}) or {}
    call_data = scored_call.get("call_data", {}) or {}
    call_id = scored_call.get("call_id", "")
    title = scored_call.get("title", "")
    fit_score_100 = _safe_float(scored_call.get("fit_score_100"), 0.0)

    dominant, dominant_value = _dominant_component(score_breakdown)
    local_scores = score_breakdown.get("local_scores", {}) or {}
    weights = score_breakdown.get("weights", {}) or {}
    solver_status = score_breakdown.get("status", "Unknown")

    sentences = [
        (
            f"Fit score del {fit_score_100:.1f}% per {call_id} '{title}', ottimizzato con AHP + Gurobi "
            f"(solver: {solver_status}, CR={_safe_float(score_breakdown.get('cr'), 0.0):.4f})."
        ),
        (
            f"Criterio dominante: {dominant} con contributo pesato {dominant_value * 100:.1f} punti su 100; "
            f"pesi AHP attivi: Excellence {weights.get('excellence', 0):.4f}, "
            f"Impact {weights.get('impact', 0):.4f}, Implementation {weights.get('implementation', 0):.4f}, "
            f"Tech Fit {weights.get('tech_fit', 0):.4f}."
        ),
        (
            f"Punteggi locali pre-LP: Excellence {local_scores.get('excellence', 0):.2f}, "
            f"Impact {local_scores.get('impact', 0):.2f}, "
            f"Implementation {local_scores.get('implementation', 0):.2f}, "
            f"Tech Fit {local_scores.get('tech_fit', 0):.2f}."
        ),
    ]

    caps = _estimate_caps(score_breakdown.get("constraints_applied", {}) or {})
    if caps:
        sentences.append("Vincoli LP attivati: " + "; ".join(caps) + ".")

    source_docs = call_data.get("source_documents") or ([call_data.get("source_document")] if call_data.get("source_document") else [])
    source_pages = call_data.get("source_pages") or []
    if source_docs:
        pages_txt = f", pagine {', '.join(str(p) for p in source_pages[:5])}" if source_pages else ""
        if len(source_pages) > 5:
            pages_txt += "…"
        sentences.append(f"Riferimento documento: {', '.join(source_docs[:2])}{pages_txt}.")

    justification = " ".join(sentences[:5])

    explanation = HorizonExplainer().generate_full_explanation(
        call=call_data,
        scores=scored_call,
        profile=company_profile,
        pdf_excerpts=None,
    )

    desc_sample = company_profile.get("description", "")[:200]
    company_hash = hashlib.md5(desc_sample.encode("utf-8")).hexdigest()
    audit_record = {
        "call_id": call_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "company_description_hash": company_hash,
        "score_breakdown": _json_safe(score_breakdown),
        "justification": justification,
    }
    _append_audit_record(audit_record, config=config)
    logger.debug("Giustificazione generata per %s", call_id)
    return justification, audit_record, explanation


def _append_audit_record(record: dict[str, Any], config: dict[str, Any] | None = None) -> None:
    effective_config = config or CONFIG
    audit_path = effective_config["audit_log"]
    try:
        os.makedirs(os.path.dirname(audit_path), exist_ok=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(_json_safe(record), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Impossibile scrivere audit log %s: %s", audit_path, exc)
