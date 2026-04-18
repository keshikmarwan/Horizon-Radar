# Horizon Radar – Note operative per Claude/Codex (stato reale)

## Obiettivo

Mantenere e migliorare una web app che fa ranking di call Horizon Europe rispetto a un profilo aziendale, con pipeline deterministica AHP + LP (Gurobi) e layer AI opzionale per spiegazioni/review.

## Architettura corrente

### Frontend

- Next.js App Router + TypeScript
- Pagine principali:
  - `/` Overview + export portfolio
  - `/fit/[id]` workspace cluster (CL1..CL6)
- Persistenza dati profilo locale via store frontend

### Backend

- FastAPI (`backend/app/api/routes.py`)
- Engine matcher (`backend/app/services/horizon_matcher/engine.py`)
- Parser PDF (`ingest.py`)
- Embedding + FAISS (`embedder.py`, `embedding_backend.py`)
- Scorer AHP + Gurobi (`scorer.py`)
- Explainability + AI review (`explainer.py`, `llm_fit_assistant.py`)
- Export report PDF (`/api/horizon-matcher/export-pdf`)

## Flusso da preservare (vincolo funzionale)

1. Upload PDF:
   - endpoint `upload-pdf`/`upload-pdfs`
   - parse e salvataggio `calls.json`
   - niente costruzione indice pesante in questa fase
2. Click su Fit (`/score`):
   - build index on-demand
   - load index
   - scoring + spiegazioni + AI review
3. Visualizzazione risultati e reasoning trace in UI

Non spostare computazione pesante dentro upload salvo richiesta esplicita.

## Modelli attuali e fallback

- LLM chat/reasoning: `OLLAMA_MODEL` (default codice: `qwen2.5:3b`)
- Embeddings: `EMBEDDING_MODEL` (default codice: `qwen3-embedding:4b`)
- `OLLAMA_THINK=true` abilita tracing `thinking`
- Se LLM non disponibile: fallback deterministico in `llm_fit_assistant.py`

## Dove compare il reasoning

- Backend: `ai_fit_review.reasoning_trace`
- Frontend: se `reasoning_available=true`, mostra blocco "Ragionamento del modello locale" nella pagina Fit dettaglio call

## Regole operative per modifiche

- Tenere AHP + Gurobi come core decisionale.
- Trattare LLM come layer opzionale (mai hard dependency bloccante).
- Conservare compatibilita con fallback locale anche se Ollama non risponde.
- Evitare regressioni del flusso upload leggero -> fit pesante on-demand.
- Aggiornare sempre documentazione quando cambia:
  - endpoint
  - env vars
  - flusso UX
  - struttura output score/explanation
