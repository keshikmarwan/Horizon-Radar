from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)
_CACHE_TTL_SECONDS = 180.0
_CACHE: dict[str, tuple[float, 'FitAssistantResult']] = {}

# ---------------------------------------------------------------------------
# Groq – API gratuita, compatibile OpenAI
# Chiave gratuita su: https://console.groq.com/
# ---------------------------------------------------------------------------
_GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
_GROQ_MODEL = 'llama-3.3-70b-versatile'


@dataclass
class FitAssistantResult:
    answer: str
    mode: str
    cached: bool
    sources: list[dict[str, Any]]


def answer_fit_query(payload: dict[str, Any]) -> FitAssistantResult:
    start = monotonic()
    force_refresh = bool(payload.get('force_refresh'))
    cache_key = _build_cache_key(payload)

    if not force_refresh:
        cached = _get_cache(cache_key)
        if cached is not None:
            return FitAssistantResult(
                answer=cached.answer, mode=cached.mode, cached=True,
                sources=[*cached.sources, {'source': 'cache', 'hit': True}],
            )

    try:
        result = _answer_with_groq(payload) if settings.groq_api_key else _answer_fallback(payload)
    except Exception as exc:
        logger.warning('fit_assistant groq failed; fallback enabled error=%s', str(exc))
        result = _answer_fallback(payload)

    _put_cache(cache_key, result)
    return result


def _answer_with_groq(payload: dict[str, Any]) -> FitAssistantResult:
    tone = _normalize_tone(payload.get('tone'))
    style = (
        'Tono executive: breve, decisionale, orientato a priorità e impatto.'
        if tone == 'executive'
        else 'Tono tecnico: preciso, con riferimenti a gap, readiness e azioni operative.'
    )
    prompt = (
        'Sei un senior consultant specializzato in bandi Horizon Europe. '
        'Rispondi SOLO in italiano. '
        f'{style} '
        'Struttura obbligatoria: 1) Diagnosi, 2) Azioni (3), 3) Rischi (max 3), 4) Decisione consigliata. '
        f'Usa solo il contesto fornito.\n\nCONTESTO JSON:\n{json.dumps(payload, ensure_ascii=False)}'
    )
    body = {
        'model': _GROQ_MODEL,
        'temperature': 0.2,
        'max_tokens': 1024,
        'messages': [
            {'role': 'system', 'content': 'Rispondi solo con contenuti utili al go/no-go del fit.'},
            {'role': 'user', 'content': prompt},
        ],
    }
    with httpx.Client(timeout=45.0) as client:
        r = client.post(_GROQ_API_URL, json=body,
                        headers={'Authorization': f'Bearer {settings.groq_api_key}', 'Content-Type': 'application/json'})
        r.raise_for_status()
    answer = r.json()['choices'][0]['message']['content'].strip()
    return FitAssistantResult(answer=answer, mode='groq', cached=False,
                              sources=[{'source': 'groq', 'model': _GROQ_MODEL, 'tone': tone}])


def _answer_fallback(payload: dict[str, Any]) -> FitAssistantResult:
    fit_score = int(payload.get('fit_score') or 0)
    recommendation = str(payload.get('recommendation') or '').upper().strip() or 'WATCH'
    tone = _normalize_tone(payload.get('tone'))
    readiness_avg = int(payload.get('readiness_avg') or 0)
    confidence_avg = int(payload.get('confidence_avg') or 0)
    nearest_deadline = payload.get('nearest_deadline')
    top_gaps = payload.get('top_gaps') or []
    top_calls = payload.get('top_calls') or []

    diagnosis = ('Fit robusto: basi concrete per procedere.' if fit_score >= 60
                 else 'Fit intermedio: gap da chiudere prima del commitment.' if fit_score >= 40
                 else 'Fit debole: strategia selettiva con forte pruning.')
    actions = [
        'Conferma entro 48h le 2 call prioritarie e assegna owner tecnico + owner partenariato.',
        'Chiudi i must-have gap con evidenze (case study, KPI, TRL, partner mancanti) in un memo unico.',
        'Prepara una bozza concept di 1 pagina per la call top, con impatto, WP preliminari e ruoli.',
    ]
    if recommendation == 'NO-GO':
        actions[0] = 'Riduci il perimetro: 1 call pilota, le altre in pausa fino a gap closure.'

    risk_lines = [
        f'- {call.get("title", f"Call #{i+1}")}: {", ".join(call.get("must_have_gaps", [])[:2]) or "gap non esplicitati"}.'
        for i, call in enumerate(top_calls[:3])
    ] or ['- Evidenze insufficienti su impatto e readiness del consorzio.']

    answer = (
        f'{diagnosis}\n\n'
        f'Indicatori: readiness {readiness_avg}/100, confidence {confidence_avg}/100.'
        + (f'\nUrgenza: deadline {nearest_deadline}.' if nearest_deadline else '')
        + (f'\nGap: {", ".join(str(g) for g in top_gaps[:3])}.' if top_gaps else '')
        + f'\n\nAzioni:\n- ' + '\n- '.join(actions)
        + f'\n\nRischi:\n' + '\n'.join(risk_lines)
        + f'\n\n{"GO condizionato a gap closure." if recommendation=="GO" else "WATCH con checkpoint 2 settimane." if recommendation=="WATCH" else "NO-GO, salva 1 opzione pilota."}'
    )
    return FitAssistantResult(answer=answer, mode='fallback', cached=False,
                              sources=[{'source': 'fallback-rule-based', 'tone': tone}])


def _normalize_tone(value: Any) -> str:
    return 'technical' if str(value or '').lower().strip() == 'technical' else 'executive'

def _build_cache_key(payload: dict[str, Any]) -> str:
    return json.dumps({k: v for k, v in payload.items() if k != 'force_refresh'},
                      sort_keys=True, ensure_ascii=True, separators=(',', ':'))

def _get_cache(key: str) -> FitAssistantResult | None:
    record = _CACHE.get(key)
    if not record:
        return None
    ts, result = record
    if monotonic() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return result

def _put_cache(key: str, result: FitAssistantResult) -> None:
    _CACHE[key] = (monotonic(), FitAssistantResult(
        answer=result.answer, mode=result.mode, cached=False, sources=list(result.sources)))
