# Cleanup Report

Data: 2026-04-14

## Obiettivo

Rendere il repository coerente e manutenibile con un solo flusso prodotto, mantenendo `apple-it/` e rimuovendo orfani/duplicati.

## Criterio applicato

1. Tenere solo ciò che serve a `Overview + Fit`.
2. Tenere solo backend matcher (`/api/horizon-matcher/*`).
3. Rimuovere route, moduli e asset legacy non referenziati.
4. Eliminare file locali/cached dal versionamento.

## Stato finale (alto livello)

- **Mantenuto**
  - `apple-it/`
  - `frontend/` (route attive: `/`, `/cluster/[id]`, `/api/auth/[...nextauth]`)
  - `backend/` (matcher API + engine/services horizon matcher)
  - `scripts/` (start + cleanup)
  - `runtime/` (solo placeholder `.gitkeep`)
  - `docs/` (criteri + report)

- **Rimosso**
  - Route/pagine legacy (`matcher`, `profiles`, `topics`, `call-viewer`, billing API).
  - Backend legacy (DB/models/tasks/connectors/dashboard/matching v2/tests/snapshots seed/init).
  - Cartelle duplicate/reference non più utili (`.claude`, `claude`, `gbionics.ai`, `reference`, `infra`, `logo_seq`).
  - PDF WP duplicati in root.
  - File env locali tracciati (`backend/.env`, `frontend/.env.local`).
  - Orfani CSS `profiles-*`.

## Verifiche eseguite

- Build frontend: `npm run build` OK.
- Compile backend: `python3 -m compileall backend/app backend/scripts` OK.
- Script pulizia aggiornato per non toccare `.git`.
