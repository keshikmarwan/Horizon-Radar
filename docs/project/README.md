# Horizon Radar

Horizon Radar is a SaaS-style web app to monitor Horizon Europe calls, detect draft work programme activity, and rank topic fit for multiple company profiles.

## MVP Scope Implemented

- FastAPI backend with pluggable connectors (`backend/app/services/connectors/*.py`)
- Daily ingestion pipeline for call data snapshots + normalized topics
- Draft Hunter pipeline for draft WP source monitoring, PDF text extraction, and version diff summary
- Company profile CRUD with multi-profile support per user
- Matching engine with embeddings + rule boosts/penalties + explainability snippets + go/no-go recommendation
- Optional OpenAI embeddings (`text-embedding-3-small`) with automatic local fallback
- Dashboard APIs for ranked topics, filtering, and topic fit detail
- Monthly report generation: HTML + PDF summary + optional SMTP digest
- Celery worker/beat scheduling for daily/monthly jobs
- Next.js frontend (Dashboard, Profiles, Topic Detail, Reports)
- Auth.js credentials-based stub and Stripe billing stub endpoint
- API tenant guard with `X-User-Id` header for profile/match scoped operations
- Dockerized local deployment with Postgres (pgvector) + Redis + backend + worker + beat + frontend
- Seed/demo scripts and connector tests (pytest + Playwright)

## Architecture

- `backend/`: API, ingestion/matching/report services, jobs, DB models, tests
- `frontend/`: Next.js app router UI
- `infra/compose/docker-compose.yml`: local full stack
- `reference/`: asset/sorgenti di ispirazione (non runtime)
- `runtime/`: log e file runtime locali
- `scripts/`: utility di manutenzione

Connector isolation:
- `funding_tenders.py`: EU Funding & Tenders call/topic source
- `ec_work_programme.py`: EC Horizon Europe work programme page
- `ncp_news.py`: Horizon Europe NCP Portal draft-related news
- `science_business.py`: Science|Business Horizon Papers secondary source

## Quick Start

Prerequisiti:
- Python 3.11+ (consigliato 3.11/3.12 su macOS)
- Node.js LTS (npm)

### macOS (un solo comando)

```bash
cd /Users/m.keshik/Desktop/GENX01/codex
./scripts/launch/start-mac.sh
```

Lo script:
- valida la versione Python
- ricrea automaticamente `.venv` se corrotta/non compatibile
- installa dipendenze backend/frontend quando serve
- inizializza DB demo (`backend/data/horizonradar.db`)
- avvia backend + frontend

### Docker (opzionale)

```powershell
docker compose -f infra/compose/docker-compose.yml up --build
```

### Avvio manuale (fallback)

```powershell
Copy-Item .env.example .env
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/init_db.py
.\.venv\Scripts\python scripts/load_demo_topics.py
.\.venv\Scripts\python scripts/seed_demo.py
.\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

cd ..\frontend
npm install
npm run dev -- -H 0.0.0.0 -p 3000
```

Open apps:
- Frontend: http://localhost:3000
- Backend OpenAPI: http://localhost:8000/docs

### Pulizia workspace

```bash
./scripts/clean-workspace.sh
```

Rimuove cache/build locali (`.next`, `__pycache__`, `.pyc`, `.DS_Store`) e prepara cartelle runtime.

## Core API Endpoints

- `POST /api/ingest`
- `POST /api/draft-hunter`
- `POST /api/reports/monthly`
- `GET /api/reports/monthly`
- `GET /api/drafts`
- `POST /api/profiles`
- `GET /api/profiles`
- `PATCH /api/profiles/{profile_id}`
- `POST /api/profiles/{profile_id}/match`
- `GET /api/topics?profile_id=...&cluster=...&trl_min=...&trl_max=...&action_type=...`
- `GET /api/topics/{topic_id}`
- `GET /api/topics/{topic_id}/fit?profile_id=...`

## Jobs

Celery Beat schedule (`backend/app/tasks/celery_app.py`):
- Daily ingestion: 03:00 UTC
- Daily draft hunter: 04:00 UTC
- Monthly report: day 1 at 06:00 UTC

## Environment Variables

See `backend/.env.example` for backend vars.

Main vars:
- `DATABASE_URL`
- `REDIS_URL`
- `SNAPSHOT_DIR` (default consigliato: `../runtime/snapshots`)
- `REPORT_DIR` (default consigliato: `../runtime/reports`)
- `OPENAI_API_KEY` (optional, current embedding is deterministic local MVP fallback)
- `EMBEDDING_PROVIDER` (`auto` or `local`)
- `EMBEDDING_MODEL` (default `text-embedding-3-small`)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` (optional)
- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_DEMO_USER_ID`
- `AUTH_SECRET`, `AUTH_URL`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (stubbed for MVP)

## API Tenant Scope

All tenant-scoped endpoints require header:

`X-User-Id: <your-user-id>`

The frontend resolves it automatically from Auth.js session (`/api/auth/session`) and falls back to `NEXT_PUBLIC_DEMO_USER_ID`.

## Testing

Run backend tests:

```powershell
docker compose exec backend pytest
```

Notes:
- Playwright test included under `backend/tests/test_connectors_playwright.py`; if browser binaries are missing, install with:

```powershell
docker compose exec backend playwright install chromium
```

## Seed + Demo

- `scripts/load_demo_topics.py`: inserts realistic example Horizon topics
- `scripts/seed_demo.py`: creates demo company profiles and computes matches

## Known MVP Limitations

- Real source pages may change HTML structure; connector parsers are intentionally isolated and easy to patch.
- Funding & Tenders parsing currently uses a generic card selector and should be hardened with source-specific regression fixtures.
- PDF report export is summary-oriented (text-first) for MVP.
- Auth and Stripe are stub-level.
