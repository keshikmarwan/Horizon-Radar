"""
explainer.py — Step 4: testo esplicativo auditabile in italiano

Genera una giustificazione in linguaggio naturale (max 5 frasi) per ogni
call nella Top 10 e registra un audit_record su data/audit_log.jsonl.
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from .config import get_matcher_config

logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()

# Termini tecnici da cercare nei testi per le citazioni esplicative
TECH_TERMS = [
    "federated learning", "health data space", "digital twin",
    "virtual human twin", "post-quantum cryptography", "cybersecurity",
    "machine learning", "artificial intelligence", "circular economy",
    "green deal", "climate neutrality", "net zero", "safe and sustainable by design",
    "gdpr", "fair data", "quantum", "pqc", "ssbd",
]


# ─── Utility ─────────────────────────────────────────────────────────────────

def _find_common_tech_terms(
    company_profile: dict,
    call: dict,
    max_terms: int = 2,
) -> list[str]:
    """
    Trova termini tecnici condivisi tra profilo aziendale e testo della call.

    Args:
        company_profile: profilo aziendale (description + technical_knowhow + keywords)
        call: dict della call (scope + expected_outcomes)
        max_terms: numero massimo di termini da restituire

    Returns:
        Lista di termini tecnici comuni (stringa originale)
    """
    profile_text = " ".join([
        company_profile.get("description", ""),
        company_profile.get("technical_knowhow", ""),
        " ".join(company_profile.get("keywords", [])),
    ]).lower()

    call_text = " ".join([
        call.get("scope") or "",
        call.get("expected_outcomes") or "",
    ]).lower()

    found = []
    for term in TECH_TERMS:
        if term in profile_text and term in call_text:
            found.append(term)
        if len(found) >= max_terms:
            break

    return found


def _dominant_component(score_breakdown: dict) -> str:
    """
    Identifica quale componente ha contribuito di più al reliability score.

    Args:
        score_breakdown: dict con valori intermedi e pesi

    Returns:
        Stringa descrittiva del componente dominante
    """
    weights = score_breakdown.get("weights_used", {})
    contributions = {
        "semantica": weights.get("semantic", 0.5) * score_breakdown.get("semantic_score", 0),
        "BM25": weights.get("bm25", 0.3) * score_breakdown.get("bm25_score", 0),
        "vincoli tecnici": weights.get("constraints", 0.2) * score_breakdown.get("constraints_score", 0),
    }
    dominant = max(contributions, key=contributions.get)
    dominant_value = contributions[dominant]
    return dominant, dominant_value


def _trl_sentence(score_breakdown: dict, call_data: dict, company_profile: dict) -> str:
    """
    Genera la frase sul TRL match/mismatch.

    Args:
        score_breakdown: dict con trl_score
        call_data: dict della call
        company_profile: profilo aziendale

    Returns:
        Stringa descrittiva del TRL match
    """
    trl_required = call_data.get("trl_required")
    trl_range = call_data.get("trl_range")
    trl_current = company_profile.get("trl_current", 5)
    trl_score = score_breakdown.get("trl_score", 0.6)

    if trl_required is None:
        return "Il documento non specifica un TRL target (punteggio neutro applicato)."

    trl_label = trl_range if trl_range else f"TRL {trl_required}"
    delta = trl_required - trl_current

    if delta <= 0:
        return (
            f"Il TRL aziendale ({trl_current}) è allineato o superiore al requisito "
            f"della call ({trl_label}), senza penalità."
        )
    elif delta == 1:
        return (
            f"Il TRL aziendale ({trl_current}) è di un livello inferiore al requisito "
            f"della call ({trl_label}): penalità lieve (−0.25)."
        )
    elif delta == 2:
        return (
            f"Il TRL aziendale ({trl_current}) è di due livelli inferiore al requisito "
            f"della call ({trl_label}): penalità moderata (−0.50)."
        )
    else:
        return (
            f"Il TRL aziendale ({trl_current}) è significativamente inferiore al requisito "
            f"della call ({trl_label}): penalità elevata (trl_score={trl_score:.2f})."
        )


def _special_conditions_sentence(score_breakdown: dict, call_data: dict, company_profile: dict) -> Optional[str]:
    """
    Genera la frase sui requisiti speciali (SSH, gender, SME, FAIR).

    Args:
        score_breakdown: dict score breakdown
        call_data: dict della call
        company_profile: profilo aziendale

    Returns:
        Frase descrittiva o None se non ci sono condizioni speciali rilevanti
    """
    conditions = call_data.get("specific_conditions", {})
    parts = []

    if conditions.get("ssh_required"):
        met = company_profile.get("ssh_capacity", False)
        parts.append(
            f"SSH ({'soddisfatto' if met else 'non soddisfatto'})"
        )
    if conditions.get("gender_dimension"):
        met = company_profile.get("gender_dimension_active", False)
        parts.append(
            f"Gender Dimension ({'soddisfatto' if met else 'non soddisfatto'})"
        )
    if conditions.get("sme_eligible") and company_profile.get("is_sme"):
        parts.append("SME eligibility (+bonus)")
    if conditions.get("fair_data"):
        met = company_profile.get("fair_compliant", False)
        parts.append(
            f"FAIR Data ({'soddisfatto' if met else 'non soddisfatto'})"
        )

    if not parts:
        return None

    return "La call richiede: " + ", ".join(parts) + "."


# ─── Core ────────────────────────────────────────────────────────────────────

def generate_justification(
    scored_call: dict,
    company_profile: dict,
    config: dict | None = None,
) -> tuple[str, dict]:
    """
    Genera il testo esplicativo in italiano per una call e registra l'audit trail.

    Produce una stringa di massimo 5 frasi che cita il reliability score,
    il componente dominante, il TRL match, i termini tecnici comuni e
    i requisiti speciali della call.

    Scrive automaticamente un audit_record in data/audit_log.jsonl.

    Args:
        scored_call: dict restituito da calculate_reliability_fit() per una call
        company_profile: profilo aziendale usato nel calcolo

    Returns:
        (justification_text, audit_record)
        - justification_text: stringa in italiano, max 5 frasi
        - audit_record: dict con timestamp, hash, breakdown, justification
    """
    score_breakdown = scored_call.get("score_breakdown", {})
    call_data = scored_call.get("call_data", {})
    call_id = scored_call.get("call_id", "")
    title = scored_call.get("title", "")
    reliability_score = scored_call.get("reliability_score", 0.0)
    score_pct = int(round(reliability_score * 100))

    # ── Frase 1: score + identità call ──────────────────────────────────────
    sentence_1 = (
        f"Affidabilità del {score_pct}% per {call_id} '{title}'."
    )

    # ── Frase 2: componente dominante ────────────────────────────────────────
    dominant, dominant_val = _dominant_component(score_breakdown)
    if dominant == "semantica":
        sem_score = score_breakdown.get("semantic_score", 0)
        sentence_2 = (
            f"Il contributo maggiore proviene dalla similarità semantica "
            f"({sem_score:.2f}/1.0): la missione aziendale è fortemente allineata "
            f"agli Expected Outcomes della call."
        )
    elif dominant == "BM25":
        bm25 = score_breakdown.get("bm25_score", 0)
        boost_txt = " (con boost per termini tecnici UE)" if score_breakdown.get("bm25_boost_applied") else ""
        sentence_2 = (
            f"Il contributo maggiore proviene dal keyword match BM25 "
            f"({bm25:.2f}/1.0){boost_txt}: la descrizione aziendale condivide "
            f"vocabolario significativo con il testo della call."
        )
    else:
        c_score = score_breakdown.get("constraints_score", 0)
        sentence_2 = (
            f"Il contributo maggiore proviene dall'allineamento tecnico-normativo "
            f"({c_score:.2f}/1.0): TRL e criteri di eligibilità sono ben soddisfatti."
        )

    # ── Frase 3: match tecnico + termini comuni ───────────────────────────────
    tech_match = score_breakdown.get("technical_match", 0)
    common_terms = _find_common_tech_terms(company_profile, call_data)
    if common_terms:
        terms_str = "'" + "' e '".join(common_terms) + "'"
        sentence_3 = (
            f"Il match tecnico è {'elevato' if tech_match >= 0.7 else 'moderato'} "
            f"({tech_match:.2f}/1.0) grazie alla presenza di termini chiave condivisi "
            f"come {terms_str}."
        )
    else:
        sentence_3 = (
            f"Il match tecnico ({tech_match:.2f}/1.0) è basato sulla similarità "
            f"semantica tra know-how aziendale e scope della call."
        )

    # ── Frase 4: TRL ─────────────────────────────────────────────────────────
    sentence_4 = _trl_sentence(score_breakdown, call_data, company_profile)

    # ── Frase 5: condizioni speciali (opzionale) ─────────────────────────────
    sentence_5 = _special_conditions_sentence(score_breakdown, call_data, company_profile)

    sentences = [sentence_1, sentence_2, sentence_3, sentence_4]
    if sentence_5:
        sentences.append(sentence_5)

    justification = " ".join(sentences[:5])

    # ── Audit record ─────────────────────────────────────────────────────────
    desc_sample = company_profile.get("description", "")[:200]
    company_hash = hashlib.md5(desc_sample.encode("utf-8")).hexdigest()

    audit_record = {
        "call_id": call_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "company_description_hash": company_hash,
        "score_breakdown": score_breakdown,
        "justification": justification,
    }

    _append_audit_record(audit_record, config=config)

    logger.debug("Giustificazione generata per %s (score=%d%%)", call_id, score_pct)
    return justification, audit_record


def _append_audit_record(record: dict, config: dict | None = None) -> None:
    """
    Appende un audit_record al file data/audit_log.jsonl (un JSON per riga).

    Crea il file se non esiste. In caso di errore di scrittura, logga il
    warning senza sollevare eccezione (il logging non deve bloccare l'app).

    Args:
        record: dizionario da serializzare come JSON
    """
    effective_config = config or CONFIG
    audit_path = effective_config["audit_log"]
    try:
        os.makedirs(os.path.dirname(audit_path), exist_ok=True)
        with open(audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug("Audit record scritto: %s", audit_path)
    except Exception as exc:
        logger.warning("Impossibile scrivere audit log: %s", exc)
