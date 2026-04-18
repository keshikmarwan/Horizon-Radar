"""
llm_explainer.py — Generazione di spiegazioni chiare in italiano usando Ollama/Qwen.

Produce la sezione `clear_explanation` con:
- testo_semplice: spiegazione in italiano piano per founder
- citazioni_dirette: estratti pertinenti dal bando
- gap_principali: ostacoli identificati
- azioni_concrete: passi operativi 3-6 mesi
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..llm.ollama_client import LLMClient, LLMClientError, get_llm_client, is_llm_available

logger = logging.getLogger(__name__)


# ─── Prompt di sistema per explainability ─────────────────────────────────────
EXPLAINABILITY_SYSTEM_PROMPT = """Sei un esperto di bandi Horizon Europe che aiuta startup deep-tech a valutare il fit con le call.

Il tuo compito è generare una spiegazione CHIARA, CONCISA e OPERATIVA per i founder di una startup.

CONTESTO:
- La startup ha già un punteggio di fit calcolato con metodo AHP + Gurobi (deterministico)
- Devi spiegare COSA SIGNIFICA quel punteggio in pratica
- Devi identificare GAP concreti e AZIONI eseguibili

STILE DI SCRITTURA:
- Italiano semplice, niente burocratese
- Frasi brevi, dirette
- Numeri e percentuali quando utili
- Niente gergo Horizon non spiegato

STRUTTURA OBBLIGATORIA DEL JSON:
{
  "testo_semplice": "stringa - max 180 caratteri, spiegazione diretta del fit",
  "citazioni_dirette": ["lista di 2-4 estratti pertinenti dal bando, max 120 char l'uno"],
  "gap_principali": ["lista di 2-5 gap identificati, specifici per questa call"],
  "azioni_concrete": ["lista di 3-6 azioni concrete per i prossimi 3-6 mesi"]
}

REGOLE PER I GAP:
- Sii specifico: non dire "TRL basso", dì "TRL 5 → 6 richiesto: serve test in ambiente operativo"
- Cita vincoli hard: SME, SSH, gender balance se applicabili
- Priorità: gap bloccanti > gap migliorativi

REGOLE PER LE AZIONI:
- Ogni azione deve avere un orizzonte temporale (es. "30 giorni", "60-90 giorni")
- Ogni azione deve essere concreta e assegnabile (es. "contattare X", "preparare Y")
- Includi almeno 1 azione su consortium building se rilevante

ESEMPIO DI OUTPUT (non copiare, adatta al caso):
{
  "testo_semplice": "Fit ottimo (72%): la call cerca esattamente la tua tecnologia di robotica per CBRN. TRL richiesto 6, sei a 5: serve demo in campo.",
  "citazioni_dirette": [
    "Tecnologie robotiche per operazioni in ambienti CBRN contaminati",
    "Dimostrazione in scenari operativi reali con primi responder"
  ],
  "gap_principali": [
    "TRL 5 → 6: manca validazione in ambiente operativo reale",
    "Consortium: serve end-user (vigili del fuoco/protezione civile) come partner"
  ],
  "azioni_concrete": [
    "Contattare Dipartimento Vigili del Fuoco per lettera di supporto (30 giorni)",
    "Pianificare demo in campo con prototipo attuale (60-90 giorni)",
    "Identificare 1-2 research organization per complementarità scientifica (45 giorni)"
  ]
}"""


def _build_user_prompt(
    call_id: str,
    title: str,
    fit_score_100: float,
    dominant_criterion: str,
    call_data: dict[str, Any],
    score_breakdown: dict[str, Any],
    profile: dict[str, Any],
) -> str:
    """Costruisce il prompt utente per la generazione della spiegazione."""

    # Estrae informazioni chiave
    trl_req = call_data.get("trl_required")
    trl_current = profile.get("trl_current", 5)
    toa = call_data.get("type_of_action", "Non specificato")
    budget = call_data.get("budget_indicative", "Non indicato")
    deadline = call_data.get("deadline", "Non indicata")

    # Estrae citazioni potenziali
    quotes = []
    for field in ("expected_outcomes", "scope"):
        text = call_data.get(field, "")
        if text:
            # Prende le prime frasi significative
            for line in text.splitlines():
                line = line.strip(" •\t-")
                if len(line) >= 40 and len(line) <= 140:
                    quotes.append(line)
                if len(quotes) >= 6:
                    break
        if len(quotes) >= 6:
            break

    # Estrae vincoli applicati
    constraints = score_breakdown.get("constraints_applied", {}) or {}
    active_constraints = []
    if constraints.get("trl_violation"):
        active_constraints.append(f"TRL violation: azienda {trl_current} < richiesto {trl_req}")
    if constraints.get("sme_required") and not constraints.get("sme_ok"):
        active_constraints.append("SME required ma azienda non certificata SME")
    if constraints.get("ssh_required"):
        active_constraints.append("SSH (social sciences) richiesto")
    if constraints.get("gender_balance_required"):
        active_constraints.append("Gender balance richiesto")

    # Punteggi locali
    local_scores = score_breakdown.get("local_scores", {}) or {}

    prompt = f"""CALL: {call_id}
TITOLO: {title}
FIT SCORE: {fit_score_100:.1f}%
CRITERIO DOMINANTE: {dominant_criterion}

DATI CALL:
- Type of Action: {toa}
- Budget: {budget}
- Deadline: {deadline}
- TRL richiesto: {trl_req if trl_req else "Non specificato"}
- TRL azienda: {trl_current}

PUNTEGGI LOCALI (pre-LP):
- Excellence: {local_scores.get('excellence', 0):.2f}
- Impact: {local_scores.get('impact', 0):.2f}
- Implementation: {local_scores.get('implementation', 0):.2f}
- Tech Fit: {local_scores.get('tech_fit', 0):.2f}

VINCOLI ATTIVI: {active_constraints if active_constraints else "Nessuno"}

ESTRATTI DAL BANDO (usa per citazioni):
{chr(10).join(f"- {q}" for q in quotes[:8])}

---
Genera ora il JSON secondo le istruzioni del system prompt.
Adatta gap e azioni al caso specifico (TRL, vincoli, fit score)."""

    return prompt


def generate_clear_explanation(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
    client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """
    Genera la sezione clear_explanation usando Qwen via API cloud.

    Args:
        call: Dati della call (con expected_outcomes, scope, ecc.)
        scores: Score breakdown con fit_score_100, local_scores, constraints
        profile: Profilo aziendale (trl_current, is_sme, ecc.)
        client: LLMClient opzionale

    Returns:
        Dizionario con testo_semplice, citazioni_dirette, gap_principali, azioni_concrete
        Oppure dizionario fallback se LLM non disponibile
    """
    if not is_llm_available():
        logger.debug("LLM non disponibile: uso fallback explainer")
        return _fallback_explanation(call, scores, profile)

    if client is None:
        client = get_llm_client()

    call_id = scores.get("call_id", call.get("id", "Unknown"))
    title = call.get("title", "Unknown")
    fit_score_100 = float(scores.get("fit_score_100", 0.0))
    score_breakdown = scores.get("score_breakdown", {}) or {}

    # Determina criterio dominante
    breakdown = score_breakdown.get("breakdown", {}) or {}
    dominant = max(breakdown, key=breakdown.get) if breakdown else "fit"
    dominant_label = {
        "excellence": "Excellence (scientifico/tecnologico)",
        "impact": "Impact (politico/strategico)",
        "implementation": "Implementation (consortium/operativo)",
        "tech_fit": "Tech Fit (allineamento scope)",
    }.get(dominant, dominant)

    try:
        messages = [
            {
                "role": "user",
                "content": _build_user_prompt(
                    call_id=call_id,
                    title=title,
                    fit_score_100=fit_score_100,
                    dominant_criterion=dominant_label,
                    call_data=call,
                    score_breakdown=score_breakdown,
                    profile=profile,
                ),
            }
        ]

        response = client.chat_with_json(
            messages=messages,
            system_prompt=EXPLAINABILITY_SYSTEM_PROMPT,
            temperature=0.2,  # Bassa per coerenza
            max_retries=1,
            think=False,
        )

        # Validazione minima della risposta
        if not isinstance(response, dict):
            raise ValueError("Risposta non è un dizionario")

        required_keys = ("testo_semplice", "citazioni_dirette", "gap_principali", "azioni_concrete")
        for key in required_keys:
            if key not in response:
                raise ValueError(f"Manca chiave {key} nella risposta")

        return _normalize_explanation(response, call, scores, profile)

    except LLMClientError as exc:
        logger.warning(f"LLM explainer fallito per {call_id}: {exc}")
        return _fallback_explanation(call, scores, profile)
    except Exception as exc:
        logger.error(f"Errore imprevisto in LLM explainer per {call_id}: {exc}")
        return _fallback_explanation(call, scores, profile)


def _normalize_explanation(
    raw: dict[str, Any],
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """Normalizza la spiegazione generata dal LLM."""

    # Testo semplice: max 180 char
    testo = str(raw.get("testo_semplice", ""))
    if len(testo) > 180:
        testo = testo[:177] + "..."

    # Citazioni: 2-4 estratti, max 120 char l'uno
    quotes = raw.get("citazioni_dirette", [])
    if not isinstance(quotes, list):
        quotes = []
    quotes = [str(q)[:120] for q in quotes if str(q).strip()][:4]

    # Gap: 2-5 elementi
    gaps = raw.get("gap_principali", [])
    if not isinstance(gaps, list):
        gaps = []
    gaps = [str(g)[:200] for g in gaps if str(g).strip()][:5]

    # Azioni: 3-6 elementi
    actions = raw.get("azioni_concrete", [])
    if not isinstance(actions, list):
        actions = []
    actions = [str(a)[:200] for a in actions if str(a).strip()][:6]

    # Criterio dominante dagli score
    breakdown = scores.get("score_breakdown", {}) or {}
    bd = breakdown.get("breakdown", {}) or {}
    dominant = max(bd, key=bd.get) if bd else "fit"

    return {
        "testo_semplice": testo,
        "citazioni_dirette": quotes,
        "gap_principali": gaps,
        "azioni_concrete": actions,
        "criterio_dominante": dominant,
    }


def _fallback_explanation(
    call: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    """
    Spiegazione fallback (senza LLM) — mantiene compatibilità.

    Usata quando LLM non è disponibile. Genera spiegazione statica
    senza richiamare explainer.py (evita loop infinito).
    """
    # Import locale per evitare circular dependency
    from ._explainer_utils import _build_static_explanation

    return _build_static_explanation(call, scores, profile)
