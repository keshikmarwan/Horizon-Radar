# AGENTS – Guida rapida per contributor AI

Questo file allinea i futuri agenti al comportamento reale dell'app.

## TL;DR

- Upload PDF deve restare leggero (solo parsing).
- Fit/score deve fare la parte pesante (embedding + FAISS + ranking).
- Core ranking = AHP + Gurobi.
- LLM/reasoning = livello aggiuntivo, non blocca il funzionamento base.

## Flusso tecnico end-to-end

1. `POST /api/horizon-matcher/upload-pdf` o `upload-pdfs`
2. Parsing Work Programme -> `calls.json` + `qa_report.json`
3. `POST /api/horizon-matcher/score`
4. `build_index(...)` on-demand
5. `load_index(...)`
6. `calculate_reliability_fit(...)`
7. `generate_justification(...)` + `generate_ai_fit_review(...)`
8. UI Fit mostra top call, score breakdown, reasoning trace (se presente)

## File chiave da conoscere

- Backend API: `backend/app/api/routes.py`
- Engine: `backend/app/services/horizon_matcher/engine.py`
- Ingest parser: `backend/app/services/horizon_matcher/ingest.py`
- Embeddings/index: `backend/app/services/horizon_matcher/embedder.py`
- Embedding backend: `backend/app/services/horizon_matcher/embedding_backend.py`
- Explainability: `backend/app/services/horizon_matcher/explainer.py`
- AI fit review + reasoning: `backend/app/services/horizon_matcher/llm_fit_assistant.py`
- Frontend Fit page: `frontend/app/fit/[id]/page.tsx`

## Config critica (.env backend)

- `OLLAMA_ENABLED`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `OLLAMA_THINK`
- `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_FALLBACK_MODEL`
- `EMBEDDING_TIMEOUT`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_CHARS`

Default correnti nel codice:

- reasoning/chat: `qwen2.5:3b`
- embeddings: `qwen3-embedding:4b`

## Anti-regressioni prima di chiudere una modifica

- Upload funziona senza avviare subito embedding globale.
- `score` funziona con indice non presente (build on-demand).
- In caso LLM down, output fallback presente e API non crasha.
- In caso modello embedding non compatibile, fallback gestito.
- UI mostra correttamente errori backend (`400/500`) con messaggi leggibili.

## Standard di modifica

- Non rimuovere campi risposta già usati dal frontend senza migrazione.
- Quando cambi payload API, aggiornare tipi frontend (`frontend/lib/types.ts`).
- Quando cambi flusso, aggiornare `README.md` e `CLAUDE.md`.
