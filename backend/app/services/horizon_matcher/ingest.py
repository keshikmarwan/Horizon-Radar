"""
ingest.py — Step 1: parsing del PDF Work Programme Horizon Europe → calls.json

Usa pdfplumber per estrarre il testo pagina per pagina, identifica le call
tramite regex sull'ID HORIZON-*, e struttura ogni call in un dizionario
normalizzato prima di salvarlo in data/calls.json.
"""

import json
import logging
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional, Sequence, Union

import pdfplumber

from .config import get_matcher_config
from .llm_extractor import extract_structured_data, merge_extraction_with_baseline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)
CONFIG = get_matcher_config()

# ─── Pattern regex ───────────────────────────────────────────────────────────

# Horizon Europe 2026-2027 format examples:
#   HORIZON-HLTH-2026-01-ENVHLTH-01
#   HORIZON-HLTH-2027-01-ENVHLTH-MISSCLIMA-03
#   HORIZON-HLTH-2027-02-DISEASE-01-two-stage
#   HORIZON-CL4-2026-D4-01 (older cluster-based format)
#   HORIZON-HLTH-2026-01-ENVHLTH-01
#   HORIZON-HLTH-2027-01-ENVHLTH-MISSCLIMA-03
#   HORIZON-HLTH-2027-02-DISEASE-01-two-stage
#   HORIZON-CL4-2026-D4-01
# Structural anchor: must end in -NN (digits) optionally followed by -two/single-stage,
# so we don't accidentally swallow trailing ToA codes (RIA, IA, CSA).
CALL_ID_PATTERN = re.compile(
    r"HORIZON-[A-Z0-9]{2,8}-\d{4}(?:-[A-Z0-9]{1,10}){1,4}-\d{1,3}(?:-(?:two|single)-stage)?"
)

# PDF running header / footer noise — must be stripped before parsing
_HEADER_FOOTER_PATTERNS = [
    re.compile(r"^\s*Horizon Europe\s*[-–]\s*Work Programme[^\n]*$", re.MULTILINE),
    re.compile(r"^\s*Part\s+\d+\s*[-–]\s*Page\s+\d+\s+of\s+\d+\s*$", re.MULTILINE),
    re.compile(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", re.MULTILINE),
    re.compile(r"^\s*EN\s*$", re.MULTILINE),
]
TRL_RANGE_PATTERN = re.compile(
    r"TRL\s*(\d)\s*(?:[-–to]+\s*TRL\s*(\d))?", re.IGNORECASE
)
FROM_TRL_PATTERN = re.compile(
    r"from\s+TRL\s*(\d)\s+to\s+TRL\s*(\d)", re.IGNORECASE
)

TOA_VALUE_PATTERNS = [
    (
        re.compile(
            r"\bpublic procurement of innovative solutions\b|\bPPI\b",
            re.IGNORECASE,
        ),
        "PPI",
    ),
    (re.compile(r"\bpre-commercial procurement\b|\bPCP\b", re.IGNORECASE), "PCP"),
    (re.compile(r"\bprogramme co-fund action\b|\bcofund\b", re.IGNORECASE), "COFUND"),
    (re.compile(r"\bcoordination and support actions?\b|\bCSA\b", re.IGNORECASE), "CSA"),
    (re.compile(r"\bresearch and innovation actions?\b|\bRIA\b", re.IGNORECASE), "RIA"),
    (re.compile(r"\binnovation actions?\b|\bIA\b", re.IGNORECASE), "IA"),
]

TOA_DEFAULT_TRL = {
    "RIA": (4, 5),
    "IA": (6, 8),
    "PCP": (6, 7),
    "PPI": (7, 8),
}

DEFAULT_ALLOWED_YEARS = {2026, 2027}

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
STANDALONE_NOISE_LINES = {
    "Health",
    "Culture, Creativity and Inclusive Society",
    "Civil Security for Society",
    "Digital, Industry and Space",
    "Climate, Energy and Mobility",
    "Food, Bioeconomy, Natural Resources, Agriculture and Environment",
}

SECTION_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "call": ("Call",),
    "specific_conditions": ("Specific conditions", "Specific condition"),
    "expected_outcomes": ("Expected Outcome", "Expected Outcomes", "Expected Impact"),
    "scope": ("Scope",),
    "type_of_action": ("Type of Action",),
    "indicative_budget": ("Indicative budget", "Budget"),
    "deadline": ("Deadline", "Opening date"),
    "eligibility": ("Eligibility", "Eligibility conditions", "Eligibility condition"),
    "award_criteria": ("Award criteria",),
    "legal_financial": (
        "Legal and financial set-up of the Grant Agreements",
        "Legal and financial set-up of the Grant",
        "Legal and financial",
    ),
    "technology_readiness_level": ("Technology readiness level",),
    "activities": ("Activities", "Activities covered"),
    "topic_description": ("Topic description",),
}

SECTION_STOP_PATTERNS = [
    re.compile(r"(?m)^[ \t]*Destination[ \t]*[-–:].*$"),
    re.compile(r"(?m)^[ \t]*Topics under this destination.*$"),
    re.compile(r"(?m)^[ \t]*Expected impacts?[ \t]*:.*$"),
    re.compile(r"(?m)^[ \t]*Proposals are invited against the following topic(?:\(s\))?:?.*$"),
]

LINE_START_CALL_ID_PATTERN = re.compile(
    rf"(?m)^\s*(?P<id>{CALL_ID_PATTERN.pattern})(?![A-Z0-9-])"
)

CALL_CONTEXT_MARKERS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bCall\s*:\s*", re.IGNORECASE), 4),
    (re.compile(r"\bSpecific conditions?\b", re.IGNORECASE), 3),
    (re.compile(r"\bType of Action\b", re.IGNORECASE), 2),
    (re.compile(r"\bExpected\s+(?:Outcomes?|Impact)\b", re.IGNORECASE), 2),
    (re.compile(r"\bScope\b", re.IGNORECASE), 2),
]


# ─── Utility functions ───────────────────────────────────────────────────────

def _clean_pdf_text(text: str) -> str:
    """
    Rimuove running header/footer e artefatti di impaginazione dal testo PDF.

    I PDF Horizon Europe ripetono su ogni pagina intestazioni come
    'Horizon Europe - Work Programme 2026-2027' e footer come
    'Part 4 - Page 43 of 211'. Questi artefatti spezzano l'estrazione
    di sezioni che si estendono su più pagine.
    """
    for pattern in _HEADER_FOOTER_PATTERNS:
        text = pattern.sub("", text)
    # pdfplumber inserts a space/newline where the PDF wraps an ID between
    # cluster and year, e.g. "HORIZON-HLTH- 2026-02-DISEASE-01". Rejoin
    # ONLY at that specific boundary to avoid sticking ToA codes (RIA, IA)
    # onto the end of an ID.
    text = re.sub(r"(HORIZON-[A-Z0-9]{2,8})-\s+(\d{4})", r"\1-\2", text)
    # Rejoin "-01-\ntwo-stage" → "-01-two-stage"
    text = re.sub(r"(-\d{1,3})-\s+(two|single)-stage\b", r"\1-\2-stage", text)
    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _strip_noise_lines(text)
    return text


def _strip_noise_lines(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        if line.strip() in STANDALONE_NOISE_LINES:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _extract_title(call_id: str, raw_text: str) -> str:
    """
    Estrae il titolo della call — può essere su più righe.

    Struttura tipica:
        HORIZON-HLTH-2026-01-ENVHLTH-01: Towards a better understanding and
        anticipation of the impacts of climate change on health
        Call: Cluster 1 - Health (Single stage - 2026)

    Il titolo è tutto ciò che sta tra l'ID+":" e la prossima intestazione
    ("Call:", "Specific conditions", o riga vuota ripetuta).
    """
    idx = raw_text.find(call_id)
    if idx < 0:
        return call_id
    rest = raw_text[idx + len(call_id):]

    # Salta ":" / "-" / em-dash iniziali
    m = re.match(r"\s*[:\-–]\s*", rest)
    if m:
        rest = rest[m.end():]

    # Termina al prossimo marker strutturale
    end_match = re.search(
        r"\n\s*(?:Call:|Specific conditions|Expected Outcome|Expected Outcomes|Expected Impact|Scope:|Type of Action|Indicative budget|Eligibility|Award criteria)",
        rest,
        re.IGNORECASE,
    )
    title_raw = rest[:end_match.start()] if end_match else rest[:400]
    # Collapse whitespace including newlines
    title = re.sub(r"\s+", " ", title_raw).strip()
    # Evita titoli troppo corti (es. solo puntini di TOC)
    if len(title) < 5 or title.count(".") > len(title) * 0.3:
        return call_id
    return title[:300]


def _compile_section_header_patterns() -> list[tuple[str, re.Pattern[str]]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for canonical, aliases in SECTION_HEADER_ALIASES.items():
        for alias in aliases:
            compiled.append(
                (
                    canonical,
                    re.compile(
                        rf"(?m)^[ \t]*{re.escape(alias)}[ \t]*:?[ \t]*",
                        re.IGNORECASE,
                    ),
                )
            )
    return compiled


SECTION_HEADER_PATTERNS = _compile_section_header_patterns()


def _find_section_headers(text: str) -> list[dict[str, Union[str, int]]]:
    headers_by_start: dict[int, dict[str, Union[str, int]]] = {}
    for canonical, pattern in SECTION_HEADER_PATTERNS:
        for match in pattern.finditer(text):
            current = headers_by_start.get(match.start())
            candidate = {
                "canonical": canonical,
                "start": match.start(),
                "content_start": match.end(),
            }
            if current is None or int(candidate["content_start"]) > int(current["content_start"]):
                headers_by_start[match.start()] = candidate
    return [headers_by_start[start] for start in sorted(headers_by_start)]


def _find_stop_positions(text: str) -> list[int]:
    positions: set[int] = set()
    for pattern in SECTION_STOP_PATTERNS:
        positions.update(match.start() for match in pattern.finditer(text))
    return sorted(positions)


def _clean_extracted_section(text: str) -> Optional[str]:
    cleaned = _strip_noise_lines(text).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned if len(cleaned) >= 15 else None


def _canonical_section_name(section_name: str) -> str:
    normalized = section_name.strip().lower()
    alias_map = {
        "expected outcome": "expected_outcomes",
        "expected outcomes": "expected_outcomes",
        "expected impact": "expected_outcomes",
        "scope": "scope",
        "type of action": "type_of_action",
        "indicative budget": "indicative_budget",
        "budget": "indicative_budget",
        "deadline": "deadline",
        "opening date": "deadline",
    }
    return alias_map.get(normalized, normalized.replace(" ", "_"))


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
    section_value = _extract_section(text, "type_of_action")
    candidates = []
    if section_value:
        candidates.append(section_value.splitlines()[0].strip())

    label_match = re.search(
        r"(?im)^[ \t]*Type of Action[ \t]*:?[ \t]*(.+)$",
        text,
    )
    if label_match:
        candidates.append(label_match.group(1).strip())

    for candidate in candidates:
        for pattern, code in TOA_VALUE_PATTERNS:
            if pattern.search(candidate):
                return code

    return None


def _extract_call_year(call_id: str) -> Optional[int]:
    """
    Estrae l'anno (YYYY) dall'ID della call.

    Returns:
        Anno come int o None se non presente.
    """
    m = re.search(r"-(\d{4})-", call_id)
    return int(m.group(1)) if m else None


def _default_trl_for_toa(type_of_action: Optional[str]) -> tuple[Optional[int], Optional[str]]:
    """
    Restituisce un TRL default coerente con il Type of Action, se disponibile.
    """
    if not type_of_action:
        return None, None
    rng = TOA_DEFAULT_TRL.get(type_of_action)
    if not rng:
        return None, None
    low, high = rng
    return low, f"TRL {low}-{high} (default ToA)"


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
    call_line_map = [
        (re.compile(r"\bCall\s*:\s*Culture, Creativity and Inclusive Society\b", re.IGNORECASE), "Culture"),
        (re.compile(r"\bCall\s*:\s*INDUSTRY\b", re.IGNORECASE), "Manufacturing"),
        (re.compile(r"\bCall\s*:\s*DIGITAL\b", re.IGNORECASE), "Digital"),
        (re.compile(r"\bCall\s*:\s*SPACE\b", re.IGNORECASE), "Space"),
        (re.compile(r"\bCall\s*:\s*CLIMATE\b", re.IGNORECASE), "Climate"),
        (re.compile(r"\bCall\s*:\s*ENERGY\b", re.IGNORECASE), "Energy"),
        (re.compile(r"\bCall\s*:\s*MOBILITY\b", re.IGNORECASE), "Mobility"),
        (re.compile(r"\bCall\s*:\s*FOOD\b", re.IGNORECASE), "Food"),
    ]
    for pattern, cluster in call_line_map:
        if pattern.search(text):
            return cluster

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
        "CL2": "Culture",
        "CL3": "Security",
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
    canonical = _canonical_section_name(section_name)
    headers = _find_section_headers(text)
    if not headers:
        return None

    matching_headers = [
        header for header in headers
        if header["canonical"] == canonical
    ]
    if not matching_headers:
        return None

    header = matching_headers[0]
    start = int(header["content_start"])
    end_candidates = [
        int(other["start"])
        for other in headers
        if int(other["start"]) > int(header["start"])
    ]
    end_candidates.extend(position for position in _find_stop_positions(text) if position > int(header["start"]))
    end = min(end_candidates) if end_candidates else len(text)
    return _clean_extracted_section(text[start:end])


def _extract_budget(text: str) -> Optional[str]:
    """
    Estrae l'indicazione di budget dal testo della call.

    Args:
        text: testo grezzo della call

    Returns:
        Stringa budget o None
    """
    section_value = _extract_section(text, "Indicative budget")
    if section_value:
        first_line = section_value.splitlines()[0].strip()
        if first_line:
            return first_line[:300]

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
    section_value = _extract_section(text, "Deadline") or _extract_section(text, "Opening date")
    if section_value:
        first_line = section_value.splitlines()[0].strip()
        if first_line:
            return first_line[:120]

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
    source_document: str,
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
    title = _extract_title(call_id, raw_text)

    type_of_action = _extract_type_of_action(raw_text)
    trl_required, trl_range = _extract_trl(raw_text)
    if trl_required is None:
        default_trl_required, default_trl_range = _default_trl_for_toa(type_of_action)
        trl_required = default_trl_required
        trl_range = default_trl_range
    specific_conditions = _extract_specific_conditions(raw_text)
    cluster = _infer_cluster(call_id, raw_text)

    expected_outcomes = (
        _extract_section(raw_text, "Expected Outcome")
        or _extract_section(raw_text, "Expected Outcomes")
        or _extract_section(raw_text, "Expected Impact")
    )
    scope = _extract_section(raw_text, "Scope")

    if expected_outcomes is None and scope is None:
        logger.warning(
            "Call %s: nessuna sezione 'Expected Outcomes' o 'Scope' trovata. "
            "Inclusa con campi a None.",
            call_id,
        )

    baseline = {
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
        "source_document": source_document,
        "source_documents": [source_document],
        "raw_text": raw_text,
    }

    # LLM extraction (opzionale, con fallback automatico)
    llm_data = extract_structured_data(call_id=call_id, raw_text=raw_text)
    if llm_data:
        logger.info("LLM extraction completata per %s", call_id)
        return merge_extraction_with_baseline(baseline, llm_data)

    return baseline


def _score_call_occurrence(window: str) -> int:
    """
    Calcola uno score di confidenza per distinguere il vero header topic
    da occorrenze in TOC o citazioni interne.
    """
    early_window = window[:2500]
    deep_window = window[:14000]
    score = 0
    for pattern, weight in CALL_CONTEXT_MARKERS:
        target = early_window if weight >= 3 else deep_window
        match = pattern.search(target)
        if not match:
            continue
        proximity_bonus = max(0, 4 - (match.start() // 500))
        score += weight + proximity_bonus
    return score


def _has_topic_structure(window: str) -> bool:
    early_window = window[:1800]
    deep_window = window[:14000]
    if not re.search(r"\bCall\s*:\s*", early_window, re.IGNORECASE):
        return False

    checks = [
        re.search(r"\bSpecific conditions?\b", early_window, re.IGNORECASE),
        re.search(r"\bType of Action\b", early_window, re.IGNORECASE),
        re.search(r"\bExpected\s+(?:Outcomes?|Impact)\b", deep_window, re.IGNORECASE),
        re.search(r"\bScope\b", deep_window, re.IGNORECASE),
    ]
    return sum(bool(match) for match in checks) >= 3


def _select_call_occurrences(
    combined_text: str,
    allowed_years: Optional[set[int]] = None,
) -> list[tuple[str, int]]:
    """
    Seleziona una sola occorrenza "migliore" per ogni call_id.

    Strategia:
    1) considera solo ID all'inizio riga;
    2) opzionalmente filtra per anno;
    3) sceglie l'occorrenza con score contesto più alto;
    4) scarta ID senza struttura topic (tipicamente TOC/citazioni);
    5) fra le occorrenze valide sceglie quella con score contesto più alto.
    """
    matches = list(LINE_START_CALL_ID_PATTERN.finditer(combined_text))
    logger.info("ID call line-start trovati: %d", len(matches))

    by_id: dict[str, list[tuple[int, int]]] = defaultdict(list)
    dropped_unstructured = 0
    for match in matches:
        call_id = match.group("id")
        year = _extract_call_year(call_id)
        if allowed_years and (year is None or year not in allowed_years):
            continue
        window = combined_text[match.end("id"): match.end("id") + 16000]
        if not _has_topic_structure(window):
            dropped_unstructured += 1
            continue
        score = _score_call_occurrence(window)
        by_id[call_id].append((match.start("id"), score))

    selected: list[tuple[str, int]] = []
    dropped_zero_score = 0
    for call_id, occurrences in by_id.items():
        # A parità di score preferisce l'occorrenza più avanti nel documento
        # (il corpo della call sta dopo TOC/sommari).
        best_start, best_score = max(occurrences, key=lambda item: (item[1], item[0]))
        if best_score <= 0:
            dropped_zero_score += 1
            continue
        selected.append((call_id, best_start))

    selected.sort(key=lambda item: item[1])
    logger.info(
        "Call uniche candidate: %d (scartate senza marker: %d, senza struttura topic: %d)",
        len(selected),
        dropped_zero_score,
        dropped_unstructured,
    )

    return selected


def _extract_calls_from_pages(
    pages_text: list[tuple[int, str]],
    source_document: str,
    allowed_years: Optional[set[int]] = None,
) -> list[dict]:
    """
    Estrae le call strutturate da un PDF già letto pagina per pagina.
    """
    cleaned_pages = [(page_num, _clean_pdf_text(text)) for page_num, text in pages_text]
    combined_text = "\n".join(text for _, text in cleaned_pages)

    selected_occurrences = _select_call_occurrences(
        combined_text=combined_text,
        allowed_years=allowed_years,
    )

    if not selected_occurrences:
        logger.warning(
            "Nessuna call valida identificata in %s. "
            "Verifica formato documento o filtro anni.",
            source_document,
        )
        return []

    starts = [start for _, start in selected_occurrences]
    calls: list[dict] = []

    for idx, (call_id, start) in enumerate(selected_occurrences):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(combined_text)
        raw_text = combined_text[start:end].strip()

        # Calcola i numeri di pagina usando lo stesso testo già pulito,
        # mantenendo coerenza con gli offset start/end.
        char_offset = 0
        source_pages: list[int] = []
        for page_num, page_text in cleaned_pages:
            page_start = char_offset
            page_end = char_offset + len(page_text) + 1
            if page_end > start and page_start < end:
                source_pages.append(page_num)
            char_offset = page_end

        call_dict = _build_call_dict(
            call_id=call_id,
            raw_text=raw_text,
            source_pages=source_pages,
            source_document=source_document,
        )
        if not call_dict.get("expected_outcomes") and not call_dict.get("scope"):
            logger.warning(
                "Call %s scartata: struttura incompleta (mancano Expected Outcomes e Scope).",
                call_id,
            )
            continue
        calls.append(call_dict)
        logger.debug("Processata call %s (doc=%s, pagine=%s)", call_id, source_document, source_pages)

    return calls


def _call_richness_score(call: dict) -> tuple[int, int]:
    """
    Punteggio per scegliere la versione migliore della stessa call_id
    quando compare in più fonti.
    """
    structure_score = (
        int(bool(call.get("expected_outcomes"))) * 3
        + int(bool(call.get("scope"))) * 3
        + int(bool(call.get("type_of_action"))) * 2
        + int(call.get("trl_required") is not None) * 1
    )
    text_len = len(call.get("raw_text") or "")
    return structure_score, text_len


def _merge_calls_by_id(calls: list[dict]) -> list[dict]:
    """
    Deduplica le call sul campo 'id', preservando la versione più ricca.
    """
    best_by_id: dict[str, dict] = {}
    for call in calls:
        call_id = call["id"]
        existing = best_by_id.get(call_id)
        if existing is None:
            best_by_id[call_id] = call
            continue

        if _call_richness_score(call) > _call_richness_score(existing):
            winner, loser = call, existing
        else:
            winner, loser = existing, call

        winner_docs = sorted(
            set(winner.get("source_documents", []) + loser.get("source_documents", []))
        )
        winner_pages = sorted(
            set((winner.get("source_pages") or []) + (loser.get("source_pages") or []))
        )
        winner["source_documents"] = winner_docs
        winner["source_pages"] = winner_pages
        best_by_id[call_id] = winner

    merged = list(best_by_id.values())
    merged.sort(key=lambda c: c["id"])
    return merged


def _save_calls(calls: list[dict], output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calls, f, ensure_ascii=False, indent=2)
    logger.info("Salvato: %s (%d call)", output_path, len(calls))


def _build_quality_report(calls: list[dict]) -> dict:
    anomalies = {
        "missing_type_of_action": [c["id"] for c in calls if not c.get("type_of_action")],
        "missing_expected_outcomes": [c["id"] for c in calls if not c.get("expected_outcomes")],
        "missing_scope": [c["id"] for c in calls if not c.get("scope")],
        "expected_outcomes_contains_scope": [
            c["id"]
            for c in calls
            if "scope:" in (c.get("expected_outcomes") or "").lower()
        ],
        "scope_contains_destination": [
            c["id"]
            for c in calls
            if "Destination -" in (c.get("scope") or "")
            or "Proposals are invited against the following topic" in (c.get("scope") or "")
        ],
        "title_fallback_to_id": [c["id"] for c in calls if c.get("title") == c["id"]],
        "non_cluster_topic_ids": [c["id"] for c in calls if "-WIDERA-" in c["id"]],
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "totals": {
            "calls": len(calls),
            "clusters": dict(Counter(c["cluster"] for c in calls)),
            "type_of_action": dict(Counter(c.get("type_of_action") or "Non specificato" for c in calls)),
        },
        "missing_counts": {
            "type_of_action": len(anomalies["missing_type_of_action"]),
            "expected_outcomes": len(anomalies["missing_expected_outcomes"]),
            "scope": len(anomalies["missing_scope"]),
        },
        "anomaly_counts": {key: len(value) for key, value in anomalies.items()},
        "anomaly_examples": {key: value[:20] for key, value in anomalies.items()},
    }


def _save_quality_report(report: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("Salvato QA report: %s", output_path)


def _print_ingest_report(calls: list[dict]) -> None:
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


def _read_pdf_pages(pdf_source: Union[str, BinaryIO]) -> tuple[list[tuple[int, str]], str]:
    """
    Legge un PDF e restituisce [(page_num, page_text)] + label documento.
    """
    if isinstance(pdf_source, str):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(
                f"PDF non trovato: '{pdf_source}'. "
                "Assicurati di aver copiato il file in data/work_programme.pdf"
            )
        logger.info("Apertura PDF da percorso: %s", pdf_source)
        pdf_input: Union[str, BinaryIO] = pdf_source
        source_document = Path(pdf_source).name
    else:
        logger.info("Apertura PDF da file-like object (upload)")
        # Rewind per sicurezza su stream riutilizzati
        try:
            pdf_source.seek(0)
        except Exception:
            pass
        pdf_input = pdf_source
        source_document = "uploaded_work_programme.pdf"

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

    return pages_text, source_document


def parse_work_programmes(
    pdf_sources: Sequence[Union[str, BinaryIO]],
    *,
    allowed_years: Optional[set[int]] = None,
    persist: bool = True,
) -> list[dict]:
    """
    Parsa più Work Programme e costruisce un unico dataset calls.json.
    """
    if not pdf_sources:
        return []

    years_filter = allowed_years if allowed_years is not None else DEFAULT_ALLOWED_YEARS
    all_calls: list[dict] = []

    for source in pdf_sources:
        pages_text, source_document = _read_pdf_pages(source)
        calls = _extract_calls_from_pages(
            pages_text=pages_text,
            source_document=source_document,
            allowed_years=years_filter,
        )
        all_calls.extend(calls)

    merged_calls = _merge_calls_by_id(all_calls)
    quality_report = _build_quality_report(merged_calls)

    if persist:
        _save_calls(merged_calls, CONFIG["calls_json"])
        _save_quality_report(quality_report, CONFIG["qa_report"])

    _print_ingest_report(merged_calls)
    return merged_calls


def parse_work_programme(
    pdf_source: Union[str, BinaryIO],
    *,
    allowed_years: Optional[set[int]] = None,
) -> list[dict]:
    """
    Parsa un singolo PDF Work Programme e salva calls.json.
    """
    return parse_work_programmes(
        [pdf_source],
        allowed_years=allowed_years,
        persist=True,
    )


# ─── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else CONFIG["pdf_path"]
    parse_work_programme(pdf_path)
