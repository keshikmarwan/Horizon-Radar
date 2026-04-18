"""
_explainer_utils.py — Utility per spiegazioni statiche (fallback LLM).

Separato per evitare circular dependency tra explainer.py e llm_explainer.py.
"""

from __future__ import annotations

from typing import Any


def _build_static_explanation(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Genera spiegazione statica fallback (senza LLM).

    Args:
        call: Dati della call
        scores: Score breakdown
        profile: Profilo aziendale

    Returns:
        Dizionario clear_explanation
    """
    call_id = scores.get("call_id", call.get("id", "Unknown"))
    fit_score_100 = float(scores.get("fit_score_100", 0.0))
    breakdown = scores.get("score_breakdown", {}) or {}
    bd = breakdown.get("breakdown", {}) or {}
    dominant = max(bd, key=bd.get) if bd else "fit"

    # Costruisce testo semplice
    clear_text = (
        f"La call {call_id} ottiene un fit del {fit_score_100:.1f}% dopo ottimizzazione LP. "
        f"Il criterio dominante e' {dominant}."
    )

    # Estrae citazioni
    quotes = _extract_quotes(call)

    # Costruisce gap e azioni
    gaps, actions = _build_gap_actions(breakdown, call)

    return {
        "testo_semplice": clear_text,
        "citazioni_dirette": quotes[:3],
        "gap_principali": gaps,
        "azioni_concrete": actions,
        "criterio_dominante": dominant,
    }


def _extract_quotes(call: dict[str, Any], max_items: int = 3) -> list[str]:
    """Estrae citazioni pertinenti dalla call."""
    excerpts: list[str] = []
    for field in ("expected_outcomes", "scope"):
        text = str(call.get(field) or "").strip()
        if not text:
            continue
        lines = [ln.strip(" •\t-") for ln in text.splitlines() if ln.strip()]
        for ln in lines:
            if len(ln) >= 60:
                excerpts.append(ln[:280] + ("…" if len(ln) > 280 else ""))
            if len(excerpts) >= max_items:
                return excerpts
    return excerpts[:max_items]


def _build_gap_actions(
    score_breakdown: dict[str, Any],
    call: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Costruisce lista di gap e azioni concrete."""
    local_scores = score_breakdown.get("local_scores", {}) or {}
    constraints = score_breakdown.get("constraints_applied", {}) or {}

    gaps: list[str] = []
    actions: list[str] = []

    def _safe_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return default

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
        trl_req = call.get("trl_required")
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
