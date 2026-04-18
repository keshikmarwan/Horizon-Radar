# LLM Integration — Horizon Radar

## Panoramica

Integrazione di LLM per migliorare:
1. Estrazione strutturata dai PDF Work Programme
2. Generazione spiegazioni in italiano per founder

Il core scoring **AHP + Gurobi resta invariato** (deterministico, spiegabile).

## Modalita supportate

### 1. Ollama locale o remoto

```env
OLLAMA_ENABLED=true
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_THINK=true
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=qwen3-embedding:4b
EMBEDDING_FALLBACK_MODEL=qwen3-embedding:4b
EMBEDDING_TIMEOUT=300
EMBEDDING_BATCH_SIZE=16
EMBEDDING_MAX_CHARS=1800
```

In questa modalita:
- non serve `LLM_API_KEY`
- il provider viene risolto automaticamente come `ollama`
- il fit usa Ollama per explainability e, in ingestione, per extraction migliorata
- con `OLLAMA_THINK=true` il backend raccoglie anche `message.thinking` e lo mostra nella UI del fit
- con `EMBEDDING_MODEL=qwen3-embedding:4b` il matcher semantico usa Ollama per generare gli embeddings della retrieval

### 2. Provider cloud

## Provider supportati

| Provider | Modello consigliato | Prezzo (input/output) | Note |
|----------|---------------------|----------------------|------|
| **OpenRouter** | `qwen/qwen-2.5-72b-instruct` | ~$0.40 / $0.80 per 1M token | Consigliato |
| **Together AI** | `Qwen/Qwen2.5-72B-Instruct` | ~$0.90 / $0.90 per 1M token | Alternativa |
| **Alibaba DashScope** | `qwen-max` | Variabile | Provider nativo |

## Configurazione rapida

### 1. Ottieni API Key

**OpenRouter** (consigliato):
1. Vai su https://openrouter.ai/keys
2. Crea account / login
3. Genera nuova API key
4. Credita almeno $5 (costo stimato: ~$1-2 per 100 call analizzate)

### 2. Configura `.env`

```env
# LLM Integration (cloud)
LLM_ENABLED=true
LLM_PROVIDER=openrouter
LLM_API_KEY=sk-or-v1-xxxxxxxxxxxx
LLM_MODEL=qwen/qwen-2.5-72b-instruct
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_TIMEOUT=120
```

### 3. Verifica

```bash
curl https://openrouter.ai/api/v1/models \
  -H "Authorization: Bearer $LLM_API_KEY" \
  | jq '.data[] | select(.id | contains("qwen"))'
```

## Variabili d'ambiente

| Variabile | Required | Default | Descrizione |
|-----------|----------|---------|-------------|
| `LLM_ENABLED` | No | `false` | Abilita/disabilita integrazione |
| `LLM_PROVIDER` | No | `openrouter` | `openrouter`, `together`, `dashscope`, `openai_compat` |
| `LLM_API_KEY` | **Sì** | — | Chiave API del provider |
| `LLM_MODEL` | No | `qwen/qwen-2.5-72b-instruct` | ID modello |
| `LLM_BASE_URL` | No | (da provider) | URL endpoint (override) |
| `LLM_TIMEOUT` | No | `120` | Timeout secondi |
| `OLLAMA_THINK` | No | `true` | Se `true`, cattura il reasoning trace dei modelli Ollama compatibili |
| `EMBEDDING_PROVIDER` | No | `ollama` | Backend embeddings: `ollama` o `sentence_transformers` |
| `EMBEDDING_MODEL` | No | `qwen3-embedding:4b` | Modello embeddings per retrieval semantico |
| `EMBEDDING_FALLBACK_MODEL` | No | `qwen3-embedding:4b` | Fallback automatico se il modello embeddings non e' supportato |
| `EMBEDDING_TIMEOUT` | No | `300` | Timeout per singola request embeddings verso Ollama |
| `EMBEDDING_BATCH_SIZE` | No | `16` | Numero testi per batch embeddings (riduce timeout su input lunghi) |
| `EMBEDDING_MAX_CHARS` | No | `1800` | Limite testo per singolo campo (scope/outcomes) prima dell'embedding |

## Costi stimati

Stima per singolo bando (estrazione + spiegazione):
- Input: ~8.000-15.000 token (testo call)
- Output: ~800-1.200 token (JSON + spiegazione)
- **Costo per call**: ~$0.01-0.02 con OpenRouter

Esempio: 100 call analizzate ≈ **$1-2 totali**

## Fallback automatico

Se LLM non è disponibile (API key mancante, timeout, errore HTTP):
- `ingest.py` → usa parser baseline (regex + euristiche)
- `explainer.py` → usa template statici

**Nessuna interruzione del servizio.**

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                     Horizon Radar                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │  PDF Input   │────▶│  Ingest      │────▶│ calls.json  │ │
│  │  (Work Prog) │     │  + LLM Ext   │     │             │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│                            │                                │
│                            │ (opzionale)                    │
│                            ▼                                │
│                     ┌──────────────┐                        │
│                     │  Cloud LLM   │                        │
│                     │  (Qwen2.5)   │                        │
│                     │  OpenRouter  │                        │
│                     └──────────────┘                        │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐ │
│  │  Company     │────▶│  Scorer      │────▶│ fit_score   │ │
│  │  Profile     │     │  AHP + LP    │     │             │ │
│  └──────────────┘     └──────────────┘     └─────────────┘ │
│                            │                                │
│                            ▼                                │
│                     ┌──────────────┐                        │
│                     │  Explainer   │                        │
│                     │  + LLM Gen   │                        │
│                     └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

## File nuovi

| File | Descrizione |
|------|-------------|
| `app/services/llm/ollama_client.py` | Client HTTP per API cloud (OpenRouter, Together, ecc.) |
| `app/services/llm/__init__.py` | Export pubblici |
| `app/services/horizon_matcher/llm_extractor.py` | Estrazione strutturata PDF |
| `app/services/horizon_matcher/llm_explainer.py` | Generazione spiegazioni |

## File modificati

| File | Modifica |
|------|----------|
| `ingest.py` | Hook per `llm_extractor` |
| `explainer.py` | Hook per `llm_explainer` |
| `.env` | Variabili LLM_* |

## Prompt ottimizzati

### Estrazione (llm_extractor.py)

- Output: **JSON strutturato**
- Campi: TRL, ToA, expected_outcomes, scope, specific_conditions, partner_types
- Istruzioni: "Non inventare dati, usa null se non trovato"

### Explainability (llm_explainer.py)

- Output: **Italiano piano per founder**
- Struttura: testo_semplice (180 char), citazioni, gap, azioni
- Timeline: azioni con scadenze (30/60/90 giorni)

## Testing

### 1. Test estrazione

```bash
# Carica Work Programme
curl -X POST http://localhost:8000/horizon-matcher/upload-pdf \
  -H "Authorization: Bearer admin" \
  -F "file=@work_programme.pdf"
```

Controlla log:
```
INFO — LLM extraction completata per HORIZON-HLTH-2026-...
```

### 2. Test spiegazione

```bash
curl -X POST http://localhost:8000/horizon-matcher/score \
  -H "Authorization: Bearer admin" \
  -H "Content-Type: application/json" \
  -d '{"profile": {"trl_current": 5, "mission": "...", ...}, "top_n": 10}'
```

Nel response, verifica:
```json
{
  "results": [{
    "explanation": {
      "clear_explanation": {
        "testo_semplice": "...",
        "citazioni_dirette": [...],
        "gap_principali": [...],
        "azioni_concrete": [...]
      }
    }
  }]
}
```

## Troubleshooting

### API key non valida

```
LLMClientError: HTTP 401: Invalid API key
```

**Soluzione**: Verifica la key su https://openrouter.ai/keys e aggiornala in `.env`.

### Timeout frequenti

```
LLMClientError: Timeout dopo 120s
```

**Soluzione**:
1. Aumenta `LLM_TIMEOUT=180` o `240`
2. Usa modello più piccolo: `LLM_MODEL=qwen/qwen-2.5-32b-instruct`

### Modello non trovato

```
LLMClientError: HTTP 400: Model not found
```

**Soluzione**: Verifica ID modello corretto:
- OpenRouter: https://openrouter.ai/models (cerca "qwen")
- Together: https://docs.together.ai/docs/models

### Costi più alti del previsto

**Ottimizzazioni**:
1. Usa modello 32B invece di 72B: `LLM_MODEL=qwen/qwen-2.5-32b-instruct`
2. Riduci `max_tokens` nei prompt (da 2048 a 1024)
3. Taglia testo input in `llm_extractor.py` (da 45000 a 25000 char)

## Sicurezza

- **API key**: Mai commitare `.env` in git
- **Dati**: I PDF Work Programme sono documenti pubblici Horizon Europe
- **Logging**: No dati sensibili nei prompt

## Provider alternativi

### Together AI

```env
LLM_PROVIDER=together
LLM_API_KEY=xxxxxxxxxxxx
LLM_MODEL=Qwen/Qwen2.5-72B-Instruct
LLM_BASE_URL=https://api.together.xyz/v1
```

### Alibaba DashScope

```env
LLM_PROVIDER=dashscope
LLM_API_KEY=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
LLM_MODEL=qwen-max
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### Provider custom (OpenAI-compatible)

```env
LLM_PROVIDER=openai_compat
LLM_API_KEY=xxxxxxxxxxxx
LLM_MODEL=qwen2.5-72b
LLM_BASE_URL=https://tuo-endpoint-custom.com/v1
```

## Roadmap

- [ ] Batch extraction (multiple call in parallelo)
- [ ] Cache risposte LLM per call_id (risparmio costi)
- [ ] Fallback automatico a modello più piccolo se 72B timeout
- [ ] Monitoring costi (tracking token/chiamata)
