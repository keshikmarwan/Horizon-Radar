# Project Structure

Questa struttura mantiene separati codice applicativo, asset di riferimento e artefatti runtime.

## Root

- `backend/` API FastAPI, servizi, modelli, script e test.
- `frontend/` web app Next.js (App Router).
- `infra/` file infrastruttura.
- `reference/` sorgenti e media di riferimento (branding, video, mirror sito madre).
- `runtime/` log e output runtime locali (creata dallo startup script).
- `scripts/` utility operative (`clean-workspace.sh`).

## Convenzioni

- File generati localmente non devono vivere nelle cartelle sorgente quando evitabile.
- Log runtime in `runtime/logs/`.
- DB locale in `backend/data/`.
- Cache build e pycache eliminabili in qualsiasi momento con `./scripts/clean-workspace.sh`.

## Avvio

- macOS: `./scripts/launch/start-mac.sh`
- lo script gestisce bootstrap e recupero automatico di `.venv` non valida.
