# Horizon Radar

Horizon Radar e` una piattaforma di **opportunity intelligence** per Horizon Europe.
Serve a trasformare documenti Work Programme e profili aziendali in decisioni operative: **GO / WATCH / NO-GO** su topic e call.

## Cosa fa questo software

1. Ingerisce contenuti Horizon (testo/PDF e topic) nel backend.
2. Costruisce ranking di fit tra profilo azienda e opportunita`.
3. Mostra una dashboard con punteggi, gap, readiness e priorita` di submission.
4. Genera una fase di fit visuale (animazione) con outcome finale.
5. Produce un **insight LLM** sul fit (diagnosi, azioni, rischi, decisione consigliata), con fallback locale se OpenAI non e` disponibile.

## Cosa deve fare in pratica (obiettivo operativo)

- Ridurre il tempo di screening delle call.
- Evidenziare subito i gap critici da chiudere.
- Supportare decisioni snelle su dove investire effort di proposal.
- Rendere tracciabile il perche` di ogni raccomandazione.

## Struttura cartelle

- `backend/`: API FastAPI, servizi di matching/report, modelli DB, test.
- `frontend/`: interfaccia Next.js (workspace cluster, fit, report, call viewer).
- `docs/`: documentazione tecnica e piano evolutivo V2.
- `infra/`: compose/template infrastrutturali.
- `scripts/`: utility operative (avvio/pulizia).
- `runtime/`: output runtime locali (log/report/snapshot).
- `reference/`: materiale di riferimento non runtime.

## Avvio rapido

1. Backend: `http://127.0.0.1:8000`
2. Frontend: `http://localhost:3000`
3. OpenAPI: `http://127.0.0.1:8000/docs`

Su macOS puoi usare:

```bash
./scripts/launch/start-mac.sh
```

## Note di manutenzione

- Esegui pulizia artefatti locali con:

```bash
./scripts/clean-workspace.sh
```

- Gli artefatti runtime/build non devono finire nel codice sorgente.

