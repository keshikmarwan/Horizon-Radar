# Merge Strategy (Codex + Claude)

## Obiettivo
Unificare la piattaforma in un solo stack operativo:
- UI Apple-style in `frontend/`
- API e motori di scoring in `backend/`
- asset/dati matcher in `backend/data/horizon_matcher`

## Stato attuale
- `horizon_matcher` è stato integrato nel backend via endpoint:
  - `GET /horizon-matcher/status`
  - `POST /horizon-matcher/score`
- UI dedicata disponibile in:
  - `frontend/app/matcher/page.tsx`
- Moduli core migrati dal worktree Claude a:
  - `backend/app/services/horizon_matcher/{ingest,embedder,scorer,explainer,config}.py`
- Script operativi:
  - `python backend/scripts/horizon_matcher_ingest.py`
  - `python backend/scripts/horizon_matcher_embed.py`

## Pulizia file (step successivo consigliato)
1. Escludere/ignorare in git solo artefatti generati:
   - `.next/`
   - `__pycache__/`
   - `.venv/`
2. Tenere una sola sorgente dati matcher:
   - `backend/data/horizon_matcher/*`
3. Trattare `/.claude/worktrees/*` come workspace temporaneo, non come runtime definitivo.

## Regola pratica
Nuove feature solo in `frontend/` + `backend/`; niente nuove app parallele (es. Streamlit separata).
