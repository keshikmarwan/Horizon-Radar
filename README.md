# Horizon Radar

Piattaforma unica in stile Apple con flusso operativo ridotto a:

1. `Overview` (`/`)
2. `Fit` (`/cluster/[id]`)

Motore di matching Horizon Europe: backend FastAPI locale, senza API esterne obbligatorie.

## Struttura attuale

- `apple-it/`: asset/reference Apple da mantenere.
- `frontend/`: UI Next.js (Overview, Fit, login).
- `backend/`: API matcher (`/api/horizon-matcher/*`).
- `scripts/`: avvio e pulizia workspace.
- `runtime/`: log/report/snapshot locali.
- `docs/`: criteri di ordine e manutenzione.

## Avvio (comando unico)

Dalla root:

```bash
./start.sh
```

Lo script avvia:

- Frontend: `http://localhost:3000`
- Backend API/OpenAPI: `http://localhost:8000/docs`

## Matcher: dati e rigenerazione indice

Il backend usa `backend/data/horizon_matcher/` come data dir.

Per rigenerare parser + indice manualmente:

```bash
cd backend
.venv/bin/python scripts/horizon_matcher_ingest.py
.venv/bin/python scripts/horizon_matcher_embed.py
```

In alternativa puoi caricare un PDF direttamente dalla UI Fit.

## Pulizia workspace

```bash
./scripts/clean-workspace.sh
```
