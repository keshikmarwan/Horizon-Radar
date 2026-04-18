"""
llm_fit_assistant.py — Review strategica del fit usando Ollama/Qwen.

Questo modulo non sostituisce il ranking AHP + Gurobi:
- legge il risultato matematico
- produce una valutazione qualitativa/operativa
- aiuta l'utente a capire se e come perseguire la call
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..llm.ollama_client import LLMClient, LLMClientError, get_llm_client, is_llm_available

logger = logging.getLogger(__name__)


FIT_ASSISTANT_SYSTEM_PROMPT = """Sei un advisor Horizon Europe per startup deep-tech.

Hai gia' a disposizione un fit score matematico calcolato con AHP + Gurobi.
Non devi sostituire il punteggio: devi fare un secondo livello di lettura strategica.

Obiettivo:
- spiegare se la call e' realmente perseguibile da questa startup
- evidenziare cosa rende il fit forte o fragile
- proporre i prossimi passi concreti per migliorare la candidabilita'

Rispondi SOLO in JSON valido con questa struttura:
{
  "strategic_verdict": "stringa breve, max 80 caratteri",
  "qualitative_fit_label": "strong_fit | conditional_fit | weak_fit",
  "summary": "stringa breve, max 260 caratteri",
  "strengths": ["2-4 punti di forza specifici"],
  "risks": ["2-5 rischi o attriti concreti"],
  "next_steps": ["3-6 azioni operative con orizzonte temporale"],
  "consortium_notes": ["0-4 note su partner o ruolo nel consorzio"],
  "ideal_role": "coordinator | tech_partner | end_user_partner | watch_only"
}

Regole:
- sii specifico su TRL, budget, implementation, consortium readiness
- se il fit matematico e' buono ma fragile, dillo chiaramente
- se vedi mismatch sostanziali, dillo senza addolcire
- non inventare requisiti non presenti nei dati
- tono: professionale, diretto, utile ai founder
"""


def _build_user_prompt(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    call_id = scores.get("call_id", call.get("id", "Unknown"))
    title = call.get("title", "Unknown")
    fit_score = float(scores.get("fit_score_100", 0.0))
    breakdown = scores.get("score_breakdown", {}) or {}
    local_scores = breakdown.get("local_scores", {}) or {}
    contributions = breakdown.get("optimal_contributions", {}) or {}
    constraints = breakdown.get("constraints_applied", {}) or {}
    expected_outcomes = str(call.get("expected_outcomes") or "")[:1800]
    scope = str(call.get("scope") or "")[:1800]

    return f"""STARTUP PROFILE
- Description: {profile.get("description", "")[:1200]}
- Mission: {profile.get("mission", "")[:500]}
- Technical know-how: {profile.get("technical_knowhow", "")[:800]}
- Keywords: {", ".join(profile.get("keywords", [])[:20])}
- TRL current: {profile.get("trl_current")}
- Budget company available: {profile.get("budget_company_available")}
- Budget max override: {profile.get("budget_max")}
- SME: {profile.get("is_sme")}
- SSH capacity: {profile.get("ssh_capacity")}
- Gender balance required: {profile.get("gender_balance_required")}

CALL
- ID: {call_id}
- Title: {title}
- Cluster: {call.get("cluster")}
- Type of Action: {call.get("type_of_action")}
- TRL required: {call.get("trl_required")}
- Budget: {call.get("budget_indicative")}
- Deadline: {call.get("deadline")}

MATHEMATICAL FIT
- Fit score: {fit_score:.1f}/100
- Weights: {breakdown.get("weights", {})}
- Local scores pre-LP: {local_scores}
- Optimal contributions post-LP: {contributions}
- Solver status: {breakdown.get("status")}
- Consistency ratio: {breakdown.get("cr")}
- Constraints applied: {constraints}

EXPECTED OUTCOMES
{expected_outcomes}

SCOPE
{scope}

Genera la review strategica in JSON valido. Non ripetere i dati in modo meccanico: interpreta il caso."""


def _build_reasoning_prompt(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    breakdown = scores.get("score_breakdown", {}) or {}
    local_scores = breakdown.get("local_scores", {}) or {}
    constraints = breakdown.get("constraints_applied", {}) or {}
    return f"""Valuta rapidamente il fit strategico e pensa in modo sintetico.

CALL
- ID: {scores.get("call_id", call.get("id", "Unknown"))}
- Title: {call.get("title", "Unknown")}
- TRL required: {call.get("trl_required")}

STARTUP
- TRL current: {profile.get("trl_current")}
- Keywords: {", ".join(profile.get("keywords", [])[:8])}

FIT
- Fit score: {float(scores.get("fit_score_100", 0.0)):.1f}/100
- Local scores: {local_scores}
- Constraints: {constraints}

Pensa in modo breve ai punti che rendono il fit forte o fragile."""


def generate_ai_fit_review(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
    client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    if not is_llm_available():
        return _fallback_fit_review(call, scores, profile, provider="disabled", model=None)

    if client is None:
        client = get_llm_client()

    try:
        user_prompt = _build_user_prompt(call, scores, profile)
        raw = client.chat_with_json(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=FIT_ASSISTANT_SYSTEM_PROMPT,
            temperature=0.2,
            max_retries=1,
            max_tokens=1800,
            think=False,
        )
        reasoning_trace = ""
        reasoning_enabled = False
        if client.provider == "ollama":
            reasoning_meta = client.chat_with_meta(
                messages=[{"role": "user", "content": _build_reasoning_prompt(call, scores, profile)}],
                system_prompt=FIT_ASSISTANT_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=512,
                think=True,
            )
            reasoning_trace = str(reasoning_meta.get("thinking", "") or "")
            reasoning_enabled = bool(reasoning_meta.get("thinking_enabled", False))
        return _normalize_fit_review(
            raw,
            scores,
            provider=client.provider,
            model=client.model,
            reasoning_trace=reasoning_trace,
            reasoning_enabled=reasoning_enabled,
        )
    except LLMClientError as exc:
        logger.warning("AI fit review fallita per %s: %s", scores.get("call_id"), exc)
        provider = getattr(client, "provider", "unavailable")
        model = getattr(client, "model", None)
        return _fallback_fit_review(call, scores, profile, provider=provider, model=model)
    except Exception as exc:
        logger.error("Errore imprevisto nella AI fit review per %s: %s", scores.get("call_id"), exc)
        provider = getattr(client, "provider", "unavailable")
        model = getattr(client, "model", None)
        return _fallback_fit_review(call, scores, profile, provider=provider, model=model)


def _normalize_fit_review(
    raw: dict[str, Any],
    scores: dict[str, Any],
    provider: str,
    model: str | None,
    reasoning_trace: str = "",
    reasoning_enabled: bool = False,
) -> dict[str, Any]:
    fit_score = float(scores.get("fit_score_100", 0.0))

    strengths = raw.get("strengths", [])
    if not isinstance(strengths, list):
        strengths = []
    strengths = [str(item)[:220] for item in strengths if str(item).strip()][:4]

    risks = raw.get("risks", [])
    if not isinstance(risks, list):
        risks = []
    risks = [str(item)[:220] for item in risks if str(item).strip()][:5]

    next_steps = raw.get("next_steps", [])
    if not isinstance(next_steps, list):
        next_steps = []
    next_steps = [str(item)[:220] for item in next_steps if str(item).strip()][:6]

    consortium_notes = raw.get("consortium_notes", [])
    if not isinstance(consortium_notes, list):
        consortium_notes = []
    consortium_notes = [str(item)[:220] for item in consortium_notes if str(item).strip()][:4]

    qualitative_fit_label = str(raw.get("qualitative_fit_label", "")).strip().lower()
    if qualitative_fit_label not in {"strong_fit", "conditional_fit", "weak_fit"}:
        qualitative_fit_label = "strong_fit" if fit_score >= 65 else "conditional_fit" if fit_score >= 40 else "weak_fit"

    ideal_role = str(raw.get("ideal_role", "")).strip().lower()
    if ideal_role not in {"coordinator", "tech_partner", "end_user_partner", "watch_only"}:
        ideal_role = "coordinator" if fit_score >= 70 else "tech_partner" if fit_score >= 45 else "watch_only"

    strategic_verdict = str(raw.get("strategic_verdict", "")).strip()[:80]
    if not strategic_verdict:
        strategic_verdict = "Fit promettente ma da qualificare" if fit_score >= 50 else "Fit fragile, serve riposizionamento"

    summary = str(raw.get("summary", "")).strip()[:260]
    if not summary:
        summary = "Il modello AI non ha restituito un riassunto utile, ma il fit matematico resta disponibile."

    reasoning_trace = reasoning_trace.strip()
    reasoning_preview = ""
    if reasoning_trace:
        reasoning_preview = reasoning_trace[:500]
        if len(reasoning_trace) > 500:
            reasoning_preview += "..."

    return {
        "enabled": True,
        "provider": provider,
        "model": model,
        "reasoning_enabled": reasoning_enabled,
        "reasoning_available": bool(reasoning_trace),
        "reasoning_preview": reasoning_preview,
        "reasoning_trace": reasoning_trace[:8000],
        "strategic_verdict": strategic_verdict,
        "qualitative_fit_label": qualitative_fit_label,
        "summary": summary,
        "strengths": strengths,
        "risks": risks,
        "next_steps": next_steps,
        "consortium_notes": consortium_notes,
        "ideal_role": ideal_role,
    }


def _fallback_fit_review(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
    provider: str,
    model: str | None,
) -> dict[str, Any]:
    breakdown = scores.get("score_breakdown", {}) or {}
    local_scores = breakdown.get("local_scores", {}) or {}
    constraints = breakdown.get("constraints_applied", {}) or {}
    fit_score = float(scores.get("fit_score_100", 0.0))
    trl_current = profile.get("trl_current")
    trl_required = call.get("trl_required")

    strengths: list[str] = []
    risks: list[str] = []
    next_steps: list[str] = []
    consortium_notes: list[str] = []

    if float(local_scores.get("tech_fit", 0.0)) >= 0.65:
        strengths.append("Buon allineamento tecnico con scope e metodologia della call.")
    if float(local_scores.get("impact", 0.0)) >= 0.6:
        strengths.append("Il posizionamento strategico sembra vicino agli expected outcomes del bando.")
    if float(local_scores.get("implementation", 0.0)) >= 0.6:
        strengths.append("L'implementation non mostra fragilita' evidenti nel piano operativo.")

    if constraints.get("trl_violation"):
        risks.append(f"TRL insufficiente: profilo a {trl_current}, call orientata a {trl_required}.")
        next_steps.append("Preparare una demo o validazione in ambiente rilevante entro 90-120 giorni.")
    if constraints.get("sme_required") and not constraints.get("sme_ok"):
        risks.append("Il requisito SME non e' soddisfatto nel profilo corrente.")
        consortium_notes.append("Valutare ingresso come partner tecnologico invece che come lead.")
    if constraints.get("ssh_required"):
        risks.append("La call richiede copertura SSH che oggi non emerge come punto forte.")
        consortium_notes.append("Aggiungere un partner SSH con ruolo chiaro su adoption e impatti sociali.")
    if float(local_scores.get("implementation", 0.0)) < 0.55:
        risks.append("Implementation debole: consorzio e piano esecutivo vanno resi piu' credibili.")
        next_steps.append("Costruire una shortlist di end-user, research org e industrial partner entro 30-45 giorni.")
    if float(local_scores.get("impact", 0.0)) < 0.55:
        risks.append("L'impatto non e' ancora espresso con KPI e casi d'uso convincenti.")
        next_steps.append("Riallineare narrative e KPI agli expected outcomes della call entro 30 giorni.")

    if not strengths:
        strengths.append("Il fit matematico offre comunque una base utile per capire dove intervenire.")
    if not risks:
        risks.append("Non emergono blocchi hard evidenti oltre ai normali rischi di execution.")
    if not next_steps:
        next_steps.append("Tradurre il fit in una go/no-go checklist e verificare partner, TRL e use case entro 30 giorni.")

    if not consortium_notes:
        consortium_notes.append("Ruolo consigliato: tech partner con forte ownership sul work package tecnico.")

    if fit_score >= 65:
        label = "strong_fit"
        verdict = "Call perseguibile con buona confidenza"
        role = "coordinator" if float(local_scores.get("implementation", 0.0)) >= 0.65 else "tech_partner"
    elif fit_score >= 40:
        label = "conditional_fit"
        verdict = "Fit interessante ma condizionato"
        role = "tech_partner"
    else:
        label = "weak_fit"
        verdict = "Fit debole allo stato attuale"
        role = "watch_only"

    return {
        "enabled": False,
        "provider": provider,
        "model": model,
        "reasoning_enabled": False,
        "reasoning_available": False,
        "reasoning_preview": "",
        "reasoning_trace": "",
        "strategic_verdict": verdict,
        "qualitative_fit_label": label,
        "summary": "Review AI non disponibile o non riuscita: uso un'analisi strategica fallback basata su score e vincoli.",
        "strengths": strengths[:4],
        "risks": risks[:5],
        "next_steps": next_steps[:6],
        "consortium_notes": consortium_notes[:4],
        "ideal_role": role,
    }
