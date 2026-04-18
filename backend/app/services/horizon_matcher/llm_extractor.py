"""
llm_extractor.py — Estrazione strutturata dai PDF Work Programme usando Ollama/Qwen.

Migliora il parsing baseline estraendo con maggiore accuratezza:
- TRL richiesto (numerico e range)
- Type of Action (RIA, IA, CSA, PCP, PPI)
- Expected Outcomes (testo strutturato)
- Scope (testo strutturato)
- Specific conditions (flag booleani)
- Budget indicativo
- Deadline
- Partner richiesti / consortium composition
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..llm.ollama_client import LLMClient, LLMClientError, get_llm_client, is_llm_available

logger = logging.getLogger(__name__)


# ─── Prompt di sistema per estrazione strutturata ─────────────────────────────
EXTRACTION_SYSTEM_PROMPT = """Sei un assistente specializzato nell'estrazione strutturata di informazioni dai bandi Horizon Europe 2026-2027.

Il tuo compito è analizzare il testo grezzo di una call e estrarre i campi richiesti in formato JSON STRICT.

REGOLE FONDAMENTALI:
1. Restituisci SOLO JSON valido, niente testo prima o dopo
2. Usa esattamente la struttura JSON specificata
3. Se un campo non è trovabile, usa null (non inventare dati)
4. Mantieni i testi in italiano o inglese come nel documento originale
5. Non aggiungere commenti o spiegazioni fuori dal JSON

CAMPI DA ESTRARRE:
- trl_required: intero (solo il valore minimo, es. 6 da "TRL 6-8")
- trl_range_str: stringa (es. "TRL 6-8")
- type_of_action: codice (RIA, IA, CSA, PCP, PPI) o null
- expected_outcomes: testo completo della sezione (max 2000 caratteri)
- scope: testo completo della sezione (max 2000 caratteri)
- budget_indicative: stringa esatta (es. "€ 5.00 million")
- deadline: stringa esatta (es. "15 September 2026")
- multi_actor: booleano (true se menzionato "multi-actor" o simile)
- ssh_required: booleano (true se "social sciences and humanities" o "SSH")
- gender_dimension: booleano (true se "gender dimension")
- sme_eligible: booleano (true se "SME" o "PMI")
- fair_data: booleano (true se "FAIR data")
- partner_types: lista di stringhe (tipi di partner richiesti, es. ["end-user", "research organization"])
- validation_context: stringa (contesto di validazione/demo menzionato)

Estrai con precisione: non confondere "expected outcomes" con "scope".
Expected Outcomes = impatti attesi a livello di policy/sistema
Scope = attività concrete finanziate, cosa fa il progetto"""


def _build_user_prompt(call_id: str, raw_text: str) -> str:
    """Costruisce il prompt utente per l'estrazione."""
    # Taglia il testo se troppo lungo (max 12000 token ~ 48000 char)
    max_len = 45000
    if len(raw_text) > max_len:
        raw_text = raw_text[:max_len] + "\n\n[... testo troncato per lunghezza ...]"

    return f"""CALL ID: {call_id}

TESTO DELLA CALL (estratto dal Work Programme Horizon Europe):

{raw_text}

---
Estrai ora i campi JSON richiesti secondo le istruzioni del system prompt.
Ricorda: SOLO JSON valido, niente altro."""


def extract_structured_data(
    call_id: str,
    raw_text: str,
    client: Optional[LLMClient] = None,
) -> dict[str, Any]:
    """
    Estrae dati strutturati da una call usando Qwen via API cloud.

    Args:
        call_id: Identificativo HORIZON-* della call
        raw_text: Testo grezzo della call dal PDF
        client: LLMClient opzionale (usa default se None)

    Returns:
        Dizionario con i campi estratti, o dizionario vuoto se fallisce
    """
    if not is_llm_available():
        logger.debug("LLM non disponibile: skip extraction")
        return {}

    if client is None:
        client = get_llm_client()

    try:
        messages = [
            {"role": "user", "content": _build_user_prompt(call_id, raw_text)}
        ]

        response = client.chat_with_json(
            messages=messages,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.1,  # Bassa per estrazione deterministica
            max_retries=1,
            think=False,
        )

        # Normalizza i campi estratti
        return _normalize_extracted_data(response)

    except LLMClientError as exc:
        logger.warning(f"LLM extraction fallita per {call_id}: {exc}")
        return {}
    except Exception as exc:
        logger.error(f"Errore imprevisto in LLM extraction per {call_id}: {exc}")
        return {}


def _normalize_extracted_data(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalizza i dati estratti dal LLM per coerenza con lo schema interno."""
    result: dict[str, Any] = {}

    # TRL
    trl_req = raw.get("trl_required")
    if isinstance(trl_req, int) and 1 <= trl_req <= 9:
        result["trl_required"] = trl_req
    trl_range = raw.get("trl_range_str")
    if trl_range and isinstance(trl_range, str):
        result["trl_range"] = trl_range[:50]

    # Type of Action
    toa = raw.get("type_of_action")
    if toa in ("RIA", "IA", "CSA", "PCP", "PPI"):
        result["type_of_action"] = toa

    # Sezioni di testo
    for field in ("expected_outcomes", "scope"):
        val = raw.get(field)
        if val and isinstance(val, str) and len(val.strip()) >= 50:
            result[field] = val.strip()[:2000]

    # Metadata
    for field in ("budget_indicative", "deadline"):
        val = raw.get(field)
        if val and isinstance(val, str) and val.strip():
            result[field] = val.strip()[:200]

    # Specific conditions (booleani)
    bool_fields = {
        "multi_actor": "multi_actor",
        "ssh_required": "ssh_required",
        "gender_dimension": "gender_dimension",
        "sme_eligible": "sme_eligible",
        "fair_data": "fair_data",
    }
    for out_key, in_key in bool_fields.items():
        val = raw.get(in_key)
        if isinstance(val, bool):
            result[out_key] = val

    # Partner types
    partners = raw.get("partner_types")
    if isinstance(partners, list) and partners:
        result["partner_types"] = [p.strip() for p in partners[:10] if p.strip()]

    # Validation context
    vc = raw.get("validation_context")
    if vc and isinstance(vc, str):
        result["validation_context"] = vc.strip()[:500]

    return result


def merge_extraction_with_baseline(
    baseline: dict[str, Any],
    llm_extracted: dict[str, Any],
) -> dict[str, Any]:
    """
    Fonde i dati estratti dal LLM con il baseline parser.

    Il LM ha priorità su:
    - trl_required / trl_range (più accurato)
    - expected_outcomes / scope (estrazione più pulita)
    - specific_conditions (più completo)

    Il baseline resta per:
    - id, title, cluster (già affidabili)
    - source_pages, source_document (metadata)
    - raw_text (sempre preservato)
    """
    merged = baseline.copy()

    # TRL: LLM ha priorità
    if "trl_required" in llm_extracted:
        merged["trl_required"] = llm_extracted["trl_required"]
    if "trl_range" in llm_extracted:
        merged["trl_range"] = llm_extracted["trl_range"]

    # ToA: LLM ha priorità se diverso
    if llm_extracted.get("type_of_action") and llm_extracted["type_of_action"] != baseline.get("type_of_action"):
        merged["type_of_action"] = llm_extracted["type_of_action"]

    # Sezioni testo: LLM ha priorità se più lungo/strutturato
    for field in ("expected_outcomes", "scope"):
        llm_val = llm_extracted.get(field)
        baseline_val = baseline.get(field)
        if llm_val:
            if not baseline_val or len(llm_val) > len(baseline_val) * 0.8:
                merged[field] = llm_val

    # Specific conditions: merge booleano (OR)
    if "specific_conditions" not in merged:
        merged["specific_conditions"] = {}

    for cond_key in ("multi_actor", "ssh_required", "gender_dimension", "sme_eligible", "fair_data"):
        llm_val = llm_extracted.get(cond_key)
        if isinstance(llm_val, bool):
            merged["specific_conditions"][cond_key] = llm_val

    # Metadata aggiuntivi
    if "budget_indicative" in llm_extracted:
        merged["budget_indicative"] = llm_extracted["budget_indicative"]
    if "deadline" in llm_extracted:
        merged["deadline"] = llm_extracted["deadline"]
    if "partner_types" in llm_extracted:
        merged["partner_types"] = llm_extracted["partner_types"]
    if "validation_context" in llm_extracted:
        merged["validation_context"] = llm_extracted["validation_context"]

    return merged
