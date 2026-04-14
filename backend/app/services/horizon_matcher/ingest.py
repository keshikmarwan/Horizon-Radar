"""
ingest.py — Step 1: parsing del PDF Work Programme Horizon Europe → calls.json

Usa pdfplumber per estrarre il testo pagina per pagina, identifica le call
tramite regex sull'ID HORIZON-*, e struttura ogni call in un dizionario
normalizzato prima di salvarlo in data/calls.json.
"""

import io
import json
import logging
import os
import re
import sys
from collections import Counter
from typing import BinaryIO, Optional, Union

import pdfplumber

from .config import get_matcher_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()

# ─── Pattern regex ───────────────────────────────────────────────────────────

CALL_ID_PATTERN = re.compile(r"HORIZON-[A-Z]+-\d{4}-[A-Z]+-\d{2,3}")
TRL_RANGE_PATTERN = re.compile(
    r"TRL\s*(\d)\s*(?:[-–to]+\s*TRL\s*(\d))?", re.IGNORECASE
)
FROM_TRL_PATTERN = re.compile(
    r"from\s+TRL\s*(\d)\s+to\s+TRL\s*(\d)", re.IGNORECASE
)

TOA_PATTERNS = {
    "Research and Innovation Action": "RIA",
    "Innovation Action": "IA",
    "Coordination and Support Action": "CSA",
    "Pre-Commercial Procurement": "PCP",
    "Public Procurement of Innovative Solutions": "PPI",
}

SPECIFIC_CONDITION_PATTERNS = {
    "multi_actor": re.compile(r"multi[\s-]actor", re.IGNORECASE),
    "ssh_required": re.compile(r"\bSSH\b|social sciences and humanities", re.IGNORECASE),
    "gender_dimension": re.compile(r"gender dimension", re.IGNORECASE),
    "sme_eligible": re.compile(r"\bSME\b|\bPMI\b|small and medium", re.IGNORECASE),
    "fair_data": re.compile(r"\bFAIR\b", re.IGNORECASE),
}

CLUSTER_KEYWORDS = {
    "Health": ["health", "medical", "clinical", "disease", "patient", "pharma"],
    "Digital": ["digital", "ai", "artificial intelligence", "data", "cyber", "software", "ict"],
    "Climate": ["climate", "environment", "carbon", "emission", "biodiversity"],
    "Energy": ["energy", "renewable", "solar", "wind", "hydrogen", "grid"],
    "Mobility": ["transport", "mobility", "vehicle", "autonomous", "rail", "aviation"],
    "Food": ["food", "agriculture", "bioeconomy", "farming", "nutrition"],
    "Space": ["space", "satellite", "earth observation", "galileo"],
    "Security": ["security", "defence", "border", "crisis", "resilience"],
    "Culture": ["culture", "creative", "media", "heritage", "tourism"],
    "Manufacturing": ["manufacturing", "industry", "production", "factory", "material"],
}

# All known section header names — used to detect section boundaries
KNOWN_SECTION_NAMES = [
    "expected outcomes", "expected outcome", "expected impact",
    "scope", "specific conditions", "specific condition",
    "indicative budget", "budget", "deadline", "opening date",
    "type of action", "funding rate", "eligibility conditions",
    "eligibility condition", "activities", "technology readiness level",
    "topic description", "proposals addressing", "keywords",
    "implementation", "justification",
]

# Compiled boundary pattern (used in _extract_section)
_SECTION_BOUNDARY = re.compile(
    r"^(?:" + "|".join(re.escape(s) for s in KNOWN_SECTION_NAMES) + r")\s*:?\s*$",
    re.IGNORECASE,
)

SECTION_HEADERS = re.compile(
    r"expected\s+outcomes?|expected\s+impact|scope|specific\s+conditions?|"
    r"budget|indicative\s+budget|deadline|opening\s+date",
    re.IGNORECASE,
)


# ─── Utility functions ───────────────────────────────────────────────────────

def _extract_trl(text: str) -> tuple[Optional[int], Optional[str]]:
    """
    Estrae TRL numerico e stringa originale dal testo.

    Cerca pattern come 'TRL 7', 'TRL 6-8', 'from TRL X to TRL Y'.
    Se è un range, usa il valore minimo come trl_required.

    Args:
        text: testo grezzo della call

    Returns:
        (trl_required, trl_range_str) — entrambi None se non trovati
    """
    from_match = FROM_TRL_PATTERN.search(text)
    if from_match:
        low = int(from_match.group(1))
        high = int(from_match.group(2))
        return low, f"TRL {low}-{high}"

    range_match = TRL_RANGE_PATTERN.search(text)
    if range_match:
        low = int(range_match.group(1))
        if range_match.group(2):
            high = int(range_match.group(2))
            return low, f"TRL {low}-{high}"
        return low, f"TRL {low}"

    return None, None


def _extract_type_of_action(text: str) -> Optional[str]:
    """
    Mappa il testo della call sul codice ToA (RIA, IA, CSA, PCP, PPI).

    Args:
        text: testo grezzo della call

    Returns:
        Codice ToA o None se non trovato
    """
    for full_name, code in TOA_PATTERNS.items():
        if full_name.lower() in text.lower():
            return code
    return None


def _extract_specific_conditions(text: str) -> dict:
    """
    Estrae i flag per le condizioni specifiche dalla call.

    Args:
        text: testo grezzo della call

    Returns:
        Dict con chiavi bool: multi_actor, ssh_required, gender_dimension,
        sme_eligible, fair_data
    """
    return {
        key: bool(pattern.search(text))
        for key, pattern in SPECIFIC_CONDITION_PATTERNS.items()
    }


def _infer_cluster(call_id: str, text: str) -> str:
    """
    Inferisce il cluster dalla call ID o dal testo.

    Tenta prima di estrarre il cluster dall'ID (es. HORIZON-HLTH → Health),
    poi fa keyword matching sul testo.

    Args:
        call_id: identificativo HORIZON-*
        text: testo grezzo della call

    Returns:
        Nome cluster (stringa) o "Unknown"
    """
    id_upper = call_id.upper()
    cluster_map = {
        "HLTH": "Health",
        "DIGITAL": "Digital",
        "CLIM": "Climate",
        "ENER": "Energy",
        "MOBIL": "Mobility",
        "FOOD": "Food",
        "SPACE": "Space",
        "SECU": "Security",
        "CULT": "Culture",
        "MAN": "Manufacturing",
        "IND": "Manufacturing",
        "CL1": "Health",
        "CL2": "Digital",
        "CL3": "Security",
        "CL4": "Manufacturing",
        "CL5": "Climate",
        "CL6": "Food",
    }
    for key, cluster in cluster_map.items():
        if f"-{key}-" in id_upper or id_upper.startswith(f"HORIZON-{key}"):
            return cluster

    text_lower = text.lower()
    scores = {
        cluster: sum(1 for kw in keywords if kw in text_lower)
        for cluster, keywords in CLUSTER_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Unknown"


def _extract_section(text: str, section_name: str) -> Optional[str]:
    """
    Estrae il contenuto di una sezione specifica dal testo della call.

    Usa un approccio riga per riga: trova l'header della sezione (con o senza
    due punti, su riga propria o inline) e raccoglie il testo fino alla
    prossima sezione nota o al prossimo ID call.

    Args:
        text: testo grezzo della call
        section_name: nome della sezione da cercare (es. "Expected Outcomes")

    Returns:
        Testo della sezione o None se non trovata / troppo breve
    """
    lines = text.split("\n")
    start_idx: Optional[int] = None
    inline_prefix = ""

    # Pattern flessibile: "Expected Outcomes" / "Expected Outcome" / con ":" finale
    header_exact = re.compile(
        rf"^\s*{re.escape(section_name)}s?\s*:?\s*$", re.IGNORECASE
    )
    header_inline = re.compile(
        rf"^\s*{re.escape(section_name)}s?\s*:\s*(.+)", re.IGNORECASE
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if header_exact.match(stripped):
            start_idx = i + 1
            break
        m = header_inline.match(stripped)
        if m:
            inline_prefix = m.group(1).strip()
            start_idx = i + 1
            break

    # Fallback: cerca il nome della sezione ovunque nella riga
    # (utile per PDF con rientri o formattazione non standard)
    if start_idx is None:
        loose = re.compile(
            rf"(?i){re.escape(section_name)}s?\s*:?\s*$"
        )
        for i, line in enumerate(lines):
            if loose.search(line.strip()):
                start_idx = i + 1
                break

    if start_idx is None:
        return None

    content_parts: list[str] = []
    if inline_prefix:
        content_parts.append(inline_prefix)

    for line in lines[start_idx:]:
        stripped = line.strip()
        # Stop at known section boundary
        if stripped and _SECTION_BOUNDARY.match(stripped):
            break
        # Stop at a new call ID
        if stripped and CALL_ID_PATTERN.match(stripped):
            break
        content_parts.append(line)

    content = "\n".join(content_parts).strip()
    # Require at least 15 chars to avoid empty/garbage extractions
    return content if len(content) >= 15 else None


def _extract_budget(text: str) -> Optional[str]:
    """
    Estrae l'indicazione di budget dal testo della call.

    Args:
        text: testo grezzo della call

    Returns:
        Stringa budget o None
    """
    pattern = re.compile(
        r"(?:indicative\s+)?budget[:\s]+([€$\d,.\s]+(?:million|billion|EUR|M€|M\s*EUR)?)",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _extract_deadline(text: str) -> Optional[str]:
    """
    Estrae la scadenza della call dal testo.

    Args:
        text: testo grezzo della call

    Returns:
        Stringa deadline o None
    """
    pattern = re.compile(
        r"deadline[:\s]+(\d{1,2}[\s./\-]\w+[\s./\-]\d{2,4}|\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


# ─── Core parsing ────────────────────────────────────────────────────────────

def _build_call_dict(
    call_id: str,
    raw_text: str,
    source_pages: list[int],
) -> dict:
    """
    Costruisce il dizionario strutturato per una singola call.

    Args:
        call_id: identificativo HORIZON-*
        raw_text: testo grezzo della call
        source_pages: numeri di pagina di provenienza

    Returns:
        Dict normalizzato con tutti i campi richiesti
    """
    title_match = re.search(
        rf"{re.escape(call_id)}\s*[:\-–]?\s*(.+?)(?:\n|$)", raw_text
    )
    title = title_match.group(1).strip() if title_match else call_id

    trl_required, trl_range = _extract_trl(raw_text)
    type_of_action = _extract_type_of_action(raw_text)
    specific_conditions = _extract_specific_conditions(raw_text)
    cluster = _infer_cluster(call_id, raw_text)

    expected_outcomes = (
        _extract_section(raw_text, "Expected Outcomes")
        or _extract_section(raw_text, "Expected Impact")
    )
    scope = _extract_section(raw_text, "Scope")

    if expected_outcomes is None and scope is None:
        logger.warning(
            "Call %s: nessuna sezione 'Expected Outcomes' o 'Scope' trovata. "
            "Inclusa con campi a None.",
            call_id,
        )

    return {
        "id": call_id,
        "title": title,
        "cluster": cluster,
        "type_of_action": type_of_action,
        "trl_required": trl_required,
        "trl_range": trl_range,
        "expected_outcomes": expected_outcomes,
        "scope": scope,
        "specific_conditions": specific_conditions,
        "budget_indicative": _extract_budget(raw_text),
        "deadline": _extract_deadline(raw_text),
        "source_pages": source_pages,
        "raw_text": raw_text,
    }


def parse_work_programme(pdf_source: Union[str, BinaryIO]) -> list[dict]:
    """
    Parsa il PDF del Work Programme Horizon Europe e restituisce le call strutturate.

    Legge il PDF pagina per pagina con pdfplumber, identifica le call tramite
    pattern regex sull'ID HORIZON-*, e per ciascuna estrae tutti i campi
    richiesti. Salva il risultato in data/calls.json.

    Accetta sia un percorso file (str) che un file-like object (BinaryIO),
    per supportare l'upload diretto dalla UI Streamlit.

    Args:
        pdf_source: percorso assoluto/relativo al PDF oppure oggetto file-like
                    (es. BytesIO da st.file_uploader)

    Returns:
        Lista di dict, uno per ogni call trovata

    Raises:
        FileNotFoundError: se pdf_source è una stringa e il file non esiste
        RuntimeError: se pdfplumber non riesce ad aprire il file
    """
    if isinstance(pdf_source, str):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(
                f"PDF non trovato: '{pdf_source}'. "
                "Assicurati di aver copiato il file in data/work_programme.pdf"
            )
        logger.info("Apertura PDF da percorso: %s", pdf_source)
        pdf_input = pdf_source
    else:
        logger.info("Apertura PDF da file-like object (upload)")
        pdf_input = pdf_source

    # ── Estrazione testo pagina per pagina ──────────────────────────────────
    pages_text: list[tuple[int, str]] = []
    try:
        with pdfplumber.open(pdf_input) as pdf:
            total_pages = len(pdf.pages)
            logger.info("Totale pagine: %d", total_pages)
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages_text.append((i, text))
                if i % 50 == 0:
                    logger.info("  Lette %d/%d pagine...", i, total_pages)
    except Exception as exc:
        raise RuntimeError(f"Errore durante l'apertura del PDF: {exc}") from exc

    # ── Identificazione dei blocchi call ────────────────────────────────────
    # Concatena tutto il testo mantenendo i riferimenti di pagina
    full_text_parts: list[tuple[int, str]] = pages_text  # (page_num, page_text)

    # Trova tutte le occorrenze di ID call nel testo completo
    combined_text = "\n".join(t for _, t in full_text_parts)

    id_matches = list(CALL_ID_PATTERN.finditer(combined_text))
    logger.info("ID call trovati nel testo: %d (possono esserci duplicati)", len(id_matches))

    if not id_matches:
        logger.warning(
            "Nessun ID call trovato nel PDF. "
            "Verifica che il pattern HORIZON-[A-Z]+-YYYY-[A-Z]+-NNN sia presente nel documento."
        )
        return []

    # Deduplica mantenendo la prima occorrenza di ogni ID
    seen_ids: set[str] = set()
    unique_matches = []
    for m in id_matches:
        cid = m.group(0)
        if cid not in seen_ids:
            seen_ids.add(cid)
            unique_matches.append(m)

    logger.info("Call uniche identificate: %d", len(unique_matches))

    # ── Segmentazione del testo per call ────────────────────────────────────
    calls: list[dict] = []
    for idx, match in enumerate(unique_matches):
        call_id = match.group(0)
        start = match.start()
        end = unique_matches[idx + 1].start() if idx + 1 < len(unique_matches) else len(combined_text)
        raw_text = combined_text[start:end].strip()

        # Calcola i numeri di pagina coperti da questa call
        char_offset = 0
        source_pages: list[int] = []
        for page_num, page_text in full_text_parts:
            page_start = char_offset
            page_end = char_offset + len(page_text) + 1  # +1 per il \n
            if page_end > start and page_start < end:
                source_pages.append(page_num)
            char_offset = page_end

        call_dict = _build_call_dict(call_id, raw_text, source_pages)
        calls.append(call_dict)
        logger.debug("Processata call %s (pagine: %s)", call_id, source_pages)

    # ── Salvataggio ─────────────────────────────────────────────────────────
    output_path = CONFIG["calls_json"]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calls, f, ensure_ascii=False, indent=2)

    logger.info("Salvato: %s (%d call)", output_path, len(calls))

    # ── Report finale ────────────────────────────────────────────────────────
    cluster_dist = Counter(c["cluster"] for c in calls)
    toa_dist = Counter(c["type_of_action"] for c in calls)

    print("\n" + "=" * 60)
    print(f"REPORT INGEST — {len(calls)} call trovate")
    print("=" * 60)
    print("\nDistribuzione per Cluster:")
    for cluster, count in cluster_dist.most_common():
        print(f"  {cluster:<20} {count:>4} call")
    print("\nDistribuzione per Type of Action:")
    for toa, count in toa_dist.most_common():
        print(f"  {toa or 'Non specificato':<30} {count:>4} call")
    print("=" * 60 + "\n")

    return calls


# ─── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG["pdf_path"]
    parse_work_programme(pdf_path)
