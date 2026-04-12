import re
from datetime import datetime

from dateutil import parser as dt_parser
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.topic import Topic
from app.services.connectors.base import NormalizedTopic
from app.services.embedding_service import EmbeddingService
from app.services.file_extract_service import extract_text_from_upload

TOPIC_ID_RE = re.compile(r'\b(HORIZON-[A-Z0-9]+(?:-[A-Z0-9]+)+)\b')
DATE_RE = re.compile(
    r'(\d{1,2}\s+[A-Za-z]{3,12}\s+20\d{2})|([A-Za-z]{3,12}\s+\d{1,2},?\s+20\d{2})|(\d{4}-\d{2}-\d{2})'
)
COMPLIANCE_KEYWORDS: dict[str, str] = {
    'lump_sum': r'\blump sum\b',
    'two_stage': r'\btwo-stage\b|\btwo stage\b',
    'admissibility': r'\badmissibility\b',
    'eligibility': r'\beligibility\b',
    'ethics': r'\bethics?\b',
    'sex_gender': r'\bsex and gender\b',
    'fair_data': r'\bFAIR data\b|\bFAIR\b',
    'open_science': r'\bopen science\b',
    'clinical_trial': r'\bclinical trial(s)?\b',
    'interoperability': r'\binteroperab',
    'regulatory': r'\bregulatory\b|\bregulation\b',
}


def _clean_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    # Strip repeated PDF page headers that break mid-topic section extraction.
    # Matches patterns like: "Part 4 - Page 29 of 211\nHorizon Europe - Work Programme 2026-2027\nHealth\n"
    text = re.sub(
        r'\nPart \d+ - Page \d+ of \d+\nHorizon Europe[^\n]*\n[^\n]{1,60}\n',
        '\n',
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _extract_section(block: str, headings: list[str]) -> str | None:
    lines = [line.strip() for line in block.splitlines()]
    if not lines:
        return None

    starts = tuple(h.lower() for h in headings)
    stop_tokens = (
        'scope',
        'expected outcome',
        'expected outcomes',
        'type of action',
        'conditions',
        'admissibility',
        'proposal page',
        'specific conditions',
        'call budget',
        'destination',
    )

    collecting = False
    out: list[str] = []
    for line in lines:
        lowered = line.lower().strip(': ')
        if not collecting and any(lowered.startswith(s) for s in starts):
            collecting = True
            remainder = re.sub(r'^[A-Za-z ]+:\s*', '', line).strip()
            if remainder:
                out.append(remainder)
            continue

        if collecting:
            if any(lowered.startswith(token) for token in stop_tokens):
                break
            out.append(line)

    joined = ' '.join(out).strip()
    return joined[:4000] if joined else None


def _extract_deadline_iso(block: str) -> str | None:
    deadline_match = re.search(r'Deadline[^:\n]*:\s*([^\n]+)', block, flags=re.IGNORECASE)
    candidates: list[str] = []
    if deadline_match:
        candidates.extend([x for x in DATE_RE.findall(deadline_match.group(1))])

    if not candidates:
        candidates.extend([x for x in DATE_RE.findall(block[:1200])])

    flattened: list[str] = []
    for c in candidates:
        if isinstance(c, tuple):
            for part in c:
                if part:
                    flattened.append(part)
        elif c:
            flattened.append(c)

    for raw in flattened:
        try:
            parsed = dt_parser.parse(raw, dayfirst=True, fuzzy=True)
            return parsed.date().isoformat()
        except Exception:
            continue
    return None


def _extract_budget(block: str) -> float | None:
    m = re.search(r'(?:EUR|€)\s*([0-9][0-9., ]+)\s*(million|m)?', block, flags=re.IGNORECASE)
    if not m:
        return None
    raw = (m.group(1) or '').replace(' ', '').replace(',', '')
    try:
        value = float(raw)
    except ValueError:
        return None
    if (m.group(2) or '').lower() in {'million', 'm'}:
        value *= 1_000_000
    return value


def _extract_action_type(block: str) -> str | None:
    m = re.search(r'Type of Action[^:\n]*:\s*([^\n]+)', block, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()[:180]
    for token in ('RIA', 'IA', 'CSA'):
        if re.search(rf'\b{token}\b', block):
            return token
    return None


def _extract_trl(block: str) -> tuple[int | None, int | None]:
    m = re.search(r'TRL\s*(\d)(?:\s*[-to]+\s*(\d))?', block, flags=re.IGNORECASE)
    if not m:
        return None, None
    trl_min = int(m.group(1))
    trl_max = int(m.group(2)) if m.group(2) else trl_min
    return trl_min, trl_max


def _extract_procedure_stage(block: str) -> str | None:
    lowered = block.lower()
    if 'two-stage' in lowered or 'two stage' in lowered:
        return 'two-stage'
    if 'single-stage' in lowered or 'single stage' in lowered:
        return 'single-stage'
    return None


def _extract_compliance_flags(block: str) -> list[str]:
    flags: list[str] = []
    for key, pattern in COMPLIANCE_KEYWORDS.items():
        if re.search(pattern, block, flags=re.IGNORECASE):
            flags.append(key)
    return flags


def parse_work_programme_text(text: str, cluster_hint: str | None = None, source_name: str = 'ec_work_programme_pdf') -> list[NormalizedTopic]:
    text = _clean_text(text)
    if not text:
        return []

    matches = list(TOPIC_ID_RE.finditer(text))
    if not matches:
        return []

    topics: list[NormalizedTopic] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        topic_id = match.group(1).strip()
        first_line = lines[0]
        if topic_id in first_line:
            title_candidate = first_line.replace(topic_id, '').strip(' -:') or (lines[1] if len(lines) > 1 else topic_id)
        else:
            title_candidate = lines[0]
        title = title_candidate[:700] if title_candidate else topic_id

        expected_outcomes = _extract_section(block, ['Expected Outcome', 'Expected Outcomes'])
        scope = _extract_section(block, ['Scope'])
        action_type = _extract_action_type(block)
        trl_min, trl_max = _extract_trl(block)
        budget_total = _extract_budget(block)
        deadline_iso = _extract_deadline_iso(block)
        procedure_stage = _extract_procedure_stage(block)
        compliance_flags = _extract_compliance_flags(block)

        topics.append(
            NormalizedTopic(
                source=source_name,
                topic_id=topic_id,
                title=title,
                cluster=cluster_hint,
                action_type=action_type,
                trl_min=trl_min,
                trl_max=trl_max,
                expected_outcomes=expected_outcomes,
                scope=scope,
                budget_total=budget_total,
                deadline_iso=deadline_iso,
                status='open',
                topic_url=None,
                metadata_json={
                    'ingested_from': 'work-programme-pdf',
                    'parser': 'wp_pdf_v1',
                    'parsed_at': datetime.utcnow().isoformat(),
                    'procedure_stage': procedure_stage,
                    'compliance_flags': compliance_flags,
                },
            )
        )

    dedup: dict[str, NormalizedTopic] = {}
    for t in topics:
        dedup[t.topic_id] = t
    return list(dedup.values())


def ingest_work_programme_pdf(
    db: Session,
    filename: str,
    content_type: str | None,
    data: bytes,
    cluster_hint: str | None = 'CL1',
) -> dict:
    text, extracted_by = extract_text_from_upload(filename, content_type, data)
    topics = parse_work_programme_text(text, cluster_hint=cluster_hint, source_name='ec_work_programme_pdf')

    embedder = EmbeddingService()
    upserted = 0
    created = 0
    updated = 0

    for t in topics:
        deadline = dt_parser.parse(t.deadline_iso) if t.deadline_iso else None
        vec = embedder.embed(f"{t.title}\n{t.expected_outcomes or ''}\n{t.scope or ''}")

        existing = db.scalars(select(Topic).where(Topic.topic_id == t.topic_id)).first()
        if existing:
            existing.source = t.source
            existing.title = t.title
            existing.cluster = t.cluster
            existing.action_type = t.action_type
            existing.trl_min = t.trl_min
            existing.trl_max = t.trl_max
            existing.expected_outcomes = t.expected_outcomes
            existing.scope = t.scope
            existing.budget_total = t.budget_total
            existing.deadline = deadline
            existing.status = t.status
            existing.topic_url = t.topic_url
            existing.metadata_json = t.metadata_json
            existing.embedding = vec
            updated += 1
        else:
            db.add(
                Topic(
                    source=t.source,
                    topic_id=t.topic_id,
                    title=t.title,
                    cluster=t.cluster,
                    action_type=t.action_type,
                    trl_min=t.trl_min,
                    trl_max=t.trl_max,
                    expected_outcomes=t.expected_outcomes,
                    scope=t.scope,
                    budget_total=t.budget_total,
                    deadline=deadline,
                    status=t.status,
                    topic_url=t.topic_url,
                    metadata_json=t.metadata_json,
                    embedding=vec,
                )
            )
            created += 1
        upserted += 1

    db.commit()

    return {
        'filename': filename,
        'extracted_by': extracted_by,
        'text_chars': len(text),
        'topics_detected': len(topics),
        'topics_upserted': upserted,
        'topics_created': created,
        'topics_updated': updated,
        'sample_topic_ids': [t.topic_id for t in topics[:10]],
    }


def ingest_work_programme_text(
    db: Session,
    text: str,
    cluster_hint: str | None = 'CL1',
) -> dict:
    cleaned_text = (text or '').strip()
    topics = parse_work_programme_text(cleaned_text, cluster_hint=cluster_hint, source_name='ec_work_programme_text')

    embedder = EmbeddingService()
    upserted = 0
    created = 0
    updated = 0

    for t in topics:
        deadline = dt_parser.parse(t.deadline_iso) if t.deadline_iso else None
        vec = embedder.embed(f"{t.title}\n{t.expected_outcomes or ''}\n{t.scope or ''}")

        existing = db.scalars(select(Topic).where(Topic.topic_id == t.topic_id)).first()
        if existing:
            existing.source = t.source
            existing.title = t.title
            existing.cluster = t.cluster
            existing.action_type = t.action_type
            existing.trl_min = t.trl_min
            existing.trl_max = t.trl_max
            existing.expected_outcomes = t.expected_outcomes
            existing.scope = t.scope
            existing.budget_total = t.budget_total
            existing.deadline = deadline
            existing.status = t.status
            existing.topic_url = t.topic_url
            existing.metadata_json = t.metadata_json
            existing.embedding = vec
            updated += 1
        else:
            db.add(
                Topic(
                    source=t.source,
                    topic_id=t.topic_id,
                    title=t.title,
                    cluster=t.cluster,
                    action_type=t.action_type,
                    trl_min=t.trl_min,
                    trl_max=t.trl_max,
                    expected_outcomes=t.expected_outcomes,
                    scope=t.scope,
                    budget_total=t.budget_total,
                    deadline=deadline,
                    status=t.status,
                    topic_url=t.topic_url,
                    metadata_json=t.metadata_json,
                    embedding=vec,
                )
            )
            created += 1
        upserted += 1

    db.commit()
    return {
        'text_chars': len(cleaned_text),
        'topics_detected': len(topics),
        'topics_upserted': upserted,
        'topics_created': created,
        'topics_updated': updated,
        'sample_topic_ids': [t.topic_id for t in topics[:10]],
    }
