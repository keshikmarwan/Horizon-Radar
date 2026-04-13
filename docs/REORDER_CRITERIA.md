# Reorder Criteria (Current Baseline)

Obiettivo: mantenere una piattaforma unica, ordinata e senza duplicazioni, conservando `apple-it` come archivio di riferimento visivo.

## 1) Flusso prodotto unico

1. `Overview` (`/`) come ingresso.
2. `Fit` (`/cluster/[id]`) come unica area operativa matcher.

Route legacy (matcher/profiles/topics/call-viewer) rimosse.

## 2) Backend unico per scoring

- API attive solo sotto `/api/horizon-matcher/*` + `/api/health`.
- Nessun modulo legacy DB/dashboard/connectors.
- Unica logica di scoring in `backend/app/services/horizon_matcher/`.

## 3) Regole cartelle

- `apple-it/`: archivio statico di riferimento, da non toccare salvo richiesta.
- `frontend/`: UI Next.js (solo Overview + Fit + auth route).
- `backend/`: FastAPI matcher.
- `scripts/`: avvio e manutenzione.
- `runtime/`: output locali non di prodotto (log/report/snapshot).
- `docs/`: documentazione di criterio e manutenzione.

## 4) Regole anti-orfani

- Qualsiasi file non importato/usato da Overview/Fit o dal backend matcher va eliminato.
- Nessun file `.env` locale tracciato in git.
- Nessuna cache/build artefact tracciata (`.next`, `__pycache__`, `.DS_Store`, ecc.).
