# Horizon Radar

Web app Next.js + FastAPI per stimare il fit tra un profilo aziendale e le call Horizon Europe.

## Cosa fa letteralmente oggi

### Flusso utente reale

1. L'utente apre `Overview` (`/`) o direttamente `Fit` (`/fit/CL1` ... `/fit/CL6`).
2. In `Fit` carica uno o piu PDF Work Programme.
3. L'upload salva i PDF e fa solo parsing in `calls.json` (non calcola subito embeddings/FAISS).
4. Quando l'utente clicca `Avvia Fit`, parte il calcolo completo:
   - build indice embeddings on-demand
   - loading FAISS + metadata
   - scoring AHP + LP (Gurobi)
   - spiegazione tecnica + AI fit review
5. UI mostra top call, score breakdown, radar axes, gap/azioni, e reasoning trace del modello (se disponibile).
6. Export PDF genera un report professionale con dettaglio call e sintesi executive.

### Endpoint backend usati dalla UI

- `GET /api/health`
- `GET /api/horizon-matcher/status`
- `POST /api/horizon-matcher/upload-pdf`
- `POST /api/horizon-matcher/upload-pdfs`
- `POST /api/horizon-matcher/score`
- `POST /api/horizon-matcher/export-pdf`

### Comportamento upload vs fit

- Upload (`upload-pdf` / `upload-pdfs`):
  - salva file
  - parse call da PDF
  - aggiorna `calls.json` e `qa_report.json`
  - ritorna `indexed_vectors = 0`
- Fit (`score`):
  - verifica dipendenze
  - costruisce indice embeddings/FAISS se assente o non aggiornato
  - calcola ranking e spiegazioni

Questo separa correttamente le due fasi: ingestione leggera in upload, computazione pesante al click su Fit.

## Stack e modelli correnti

- Frontend: Next.js 14 + TypeScript + Tailwind
- Backend: FastAPI + FAISS + rank_bm25 + scipy + sentence-transformers + gurobipy + WeasyPrint
- LLM response/reasoning (Ollama): `qwen2.5:3b`
- Embeddings (Ollama): `qwen3-embedding:4b`
- Reasoning trace: campo `thinking` di Ollama, esposto in UI come "Ragionamento del modello locale"

## Config env rilevante (`backend/.env`)

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

## Struttura repository

- `frontend/` UI Overview/Fit
- `backend/` API + matcher engine + parser + scorer + export PDF
- `backend/data/horizon_matcher/` dataset runtime (`calls.json`, `index.faiss`, `metadata.json`, `qa_report.json`, `audit_log.jsonl`)
- `scripts/` utility di avvio/cleanup
- `runtime/` report/snapshot locali

## Avvio

Da root:

```bash
./start.sh
```

- Frontend: `http://localhost:3000`
- Backend docs: `http://localhost:8000/docs`

## Script utili backend

```bash
cd backend
.venv/bin/python scripts/horizon_matcher_ingest.py
.venv/bin/python scripts/horizon_matcher_embed.py
```

## Pulizia workspace

```bash
./scripts/clean-workspace.sh
```
