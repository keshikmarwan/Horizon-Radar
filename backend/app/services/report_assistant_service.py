from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.services.report_service import (
    collect_brokerage_report_items,
    collect_deadline_alert_items,
    collect_draft_report_items,
)

settings = get_settings()
_GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
_GROQ_MODEL = 'llama-3.3-70b-versatile'

CURATED_2026_DEADLINES = [
    {'date': '2026-03-17', 'label': 'ERC Proof of Concept (cut-off 1)'},
    {'date': '2026-03-31', 'label': 'Cluster 5: Climate, Energy & Mobility (alcuni topic)'},
    {'date': '2026-04-08', 'label': 'MSCA COFUND'},
    {'date': '2026-04-14', 'label': 'Cluster 6: Food, Bioeconomy, Agriculture (varie call, incl. Farm2Fork)'},
    {'date': '2026-04-15', 'label': 'Cluster 1: Health (es. staying healthy, digital health)'},
    {'date': '2026-04-16', 'label': 'MSCA Staff Exchanges'},
    {'date': '2026-05-12', 'label': 'EIC Pathfinder Open'},
    {'date': '2026-06-16', 'label': 'Research Infrastructures calls'},
    {'date': '2026-08-27', 'label': 'ERC Advanced Grant'},
    {'date': '2026-09-09', 'label': 'MSCA Postdoctoral Fellowships'},
    {'date': '2026-09-10', 'label': 'Cluster 5 (main round)'},
    {'date': '2026-09-16', 'label': 'Cluster 2 (Culture & Society)'},
    {'date': '2026-09-23', 'label': 'Cluster 6 (main round)'},
    {'date': '2026-10-18', 'label': 'Cluster 3 & 4 (Security + Digital/Industry/Space)'},
    {'date': '2026-11-24', 'label': 'MSCA Doctoral Networks'},
    {'date': '2026-12-01', 'label': 'Alcune call Cluster 1 Health (second window)'},
]

CURATED_DEADLINE_SOURCES = [
    {
        'title': 'EU Funding Deadlines 2026',
        'source': 'grantsfinder',
        'link': 'https://www.grantsfinder.eu/blog/eu-funding-deadlines-2026',
        'explanation': 'Fonte editoriale di riepilogo scadenze 2026.',
    },
    {
        'title': 'Horizon Europe 2026 Calls and Info Days',
        'source': 'eugrants4u',
        'link': 'https://eugrants4u.eu/horizon-europe-2026-calls-and-info-days/',
        'explanation': 'Fonte editoriale con panoramica call e info days 2026.',
    },
]


@dataclass
class AssistantResult:
    answer: str
    sources: list[dict]


def answer_report_query(query: str) -> AssistantResult:
    deadlines = collect_deadline_alert_items()
    drafts = collect_draft_report_items()
    brokerage = collect_brokerage_report_items()

    context = {
        'deadlines': deadlines[:40],
        'drafts': drafts[:20],
        'brokerage': brokerage[:25],
    }

    if settings.groq_api_key:
        try:
            return _answer_with_groq(query, context)
        except Exception:
            pass

    return _answer_fallback(query, context)


def _answer_with_groq(query: str, context: dict) -> AssistantResult:
    prompt = (
        'Sei un assistente Horizon Europe per report operativi. '
        'Rispondi in italiano in modo sintetico e pratico. '
        'Se l utente chiede deadline, dai un mini calendario per mese. '
        'Se chiede brokerage, elenca solo eventi futuri rilevanti con data e link. '
        'Se chiede draft, evidenzia i nuovi documenti o work programmes. '
        'Usa solo i dati forniti nel contesto.\n\n'
        f'QUERY UTENTE:\n{query}\n\n'
        f'CONTESTO JSON:\n{json.dumps(context, ensure_ascii=True)}'
    )
    payload = {
        'model': _GROQ_MODEL,
        'messages': [
            {'role': 'system', 'content': 'Rispondi solo sulla base del contesto fornito.'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.2,
        'max_tokens': 1024,
    }
    headers = {
        'Authorization': f'Bearer {settings.groq_api_key}',
        'Content-Type': 'application/json',
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(_GROQ_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    answer = data['choices'][0]['message']['content'].strip()
    sources = _pick_sources(query, context)
    return AssistantResult(answer=answer, sources=sources)


def _answer_fallback(query: str, context: dict) -> AssistantResult:
    q = query.lower().strip()

    if q in {'ciao', 'hello', 'hi', 'salve', 'buongiorno', 'buonasera', 'hey'}:
        return AssistantResult(
            'Ciao. Posso aiutarti su tre cose: prossime deadline Horizon, brokerage events nei prossimi mesi, nuovi draft work programme.',
            []
        )

    if any(k in q for k in ['brokerage', 'event', 'matchmaking']):
        items = context['brokerage'][:10]
        if not items:
            return AssistantResult('Non ho trovato brokerage events utili nelle fonti monitorate.', [])
        lines = ['Prossimi brokerage events trovati nei prossimi mesi:']
        for item in items:
            date = item.get('date') or 'data non rilevata'
            location = f" | {item['location']}" if item.get('location') else ''
            lines.append(f'- {date} - {item["title"]}{location}')
        return AssistantResult('\n'.join(lines), items)

    if any(k in q for k in ['draft', 'work programme', 'work program']):
        items = context['drafts'][:10]
        if not items:
            return AssistantResult('Non ho trovato nuovi draft utili nelle fonti monitorate.', [])
        lines = ['Ultimi draft rilevati:']
        for item in items:
            lines.append(f'- {item["title"]} ({item["source"]})')
        return AssistantResult('\n'.join(lines), items)

    if any(k in q for k in ['deadline', 'deadlines', 'call', 'calls', 'scadenz', 'horizon']):
        return _answer_curated_deadlines()

    return AssistantResult(
        'Non ho capito la richiesta. Prova con una domanda operativa come: "dimmi le prossime deadline Horizon", "trova i brokerage events nei prossimi 5 mesi" oppure "ci sono nuovi draft work programme?"',
        []
    )


def _pick_sources(query: str, context: dict) -> list[dict]:
    q = query.lower()
    if any(k in q for k in ['brokerage', 'event', 'matchmaking']):
        return context['brokerage'][:8]
    if any(k in q for k in ['draft', 'work programme', 'work program']):
        return context['drafts'][:8]
    return CURATED_DEADLINE_SOURCES


def _filter_upcoming_deadlines(items: list[dict]) -> list[dict]:
    now = datetime.utcnow()
    upcoming: list[dict] = []
    for item in items:
        try:
            deadline = datetime.fromisoformat(str(item['deadline']).replace('Z', '+00:00'))
        except Exception:
            continue
        if deadline.replace(tzinfo=None) >= now:
            upcoming.append(item)
    upcoming.sort(key=lambda x: x['deadline'])
    return upcoming


def _format_month(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime('%B %Y')
    except Exception:
        return value[:7]


def _format_date(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime('%d %b %Y')
    except Exception:
        return value


def _answer_curated_deadlines() -> AssistantResult:
    grouped: dict[str, list[dict]] = {}
    for item in CURATED_2026_DEADLINES:
        month = _format_month(item['date'])
        grouped.setdefault(month, []).append(item)

    lines = ['Mini calendario pratico delle prossime deadline Horizon 2026:']
    for month, values in grouped.items():
        lines.append(f'')
        lines.append(month)
        for item in values:
            lines.append(f"- {_format_date(item['date'])} - {item['label']}")
    lines.append('')
    lines.append('In pratica: aprile e settembre-ottobre sono i blocchi piu` densi.')
    return AssistantResult('\n'.join(lines), CURATED_DEADLINE_SOURCES)

