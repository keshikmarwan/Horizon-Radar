# Horizon Radar - Piano Tecnico V2 (Opportunity Intelligence)

## 1) Obiettivo
Portare l'app da matching euristico/keyword a motore di opportunity intelligence con:
- scoring multi-dimensionale;
- hard filters deterministici;
- retrieval semantico su sezioni strutturate;
- explainability auditabile;
- gap analysis e next actions operativi.

## 2) Stato attuale (as-is verificato)
### Componenti chiave già presenti
- Ingestion/upsert topic: `backend/app/services/ingestion_service.py`
- Parsing work programme PDF: `backend/app/services/work_programme_pdf_service.py`
- Matching attuale (semantic cosine + regole): `backend/app/services/matching_service.py`
- Embeddings service: `backend/app/services/embedding_service.py`
- Dashboard decisionale: `backend/app/services/dashboard_service.py`
- API: `backend/app/api/routes.py`
- Fit lato frontend (keyword-heavy): `frontend/lib/fit.ts`

### Limiti principali attuali
- scoring fortemente keyword/rule driven;
- topic salvato come record "piatto" (sezioni non normalizzate);
- profilo azienda poco strutturato (capability/evidence non separati);
- explainability limitata (`gaps` string + snippets);
- logica fit ancora parzialmente in frontend (`frontend/lib/fit.ts`).

## 3) Target architecture (to-be)

```text
Connectors/Import
  -> Raw Document Store
  -> Parser + Structuring
  -> Topic Section Extraction
  -> Enrichment (taxonomy/flags)
  -> Embedding Index
  -> Hard Filters
  -> Semantic Retrieval
  -> LLM Rubric Reranking
  -> Gap/Readiness/Partner Analysis
  -> Dashboard/API/Alerts/Report
```

Principio: separare ingestione, enrichment, retrieval, scoring, explanation e reporting.

## 4) Data model V2

## 4.1 Nuove tabelle
### `topic_sections`
- `id`
- `topic_id` (FK topics)
- `section_type` (`expected_outcome|scope|impacts|eligibility|procedure|call_overview`)
- `text`
- `page_ref`
- `embedding` (JSON inizialmente; pgvector successivo)
- `created_at`, `updated_at`

### `profile_capabilities`
- `id`
- `profile_id` (FK company_profiles)
- `name`
- `description`
- `domain_tags` (JSON list)
- `maturity_level`
- `keywords` (JSON list)
- `embedding`

### `profile_evidence`
- `id`
- `profile_id` (FK company_profiles)
- `evidence_type` (`project|publication|pilot|product|trial|dataset|certification`)
- `title`
- `summary`
- `year`
- `partners` (JSON list)
- `outcomes`
- `embedding`

### `match_results_v2`
- `id`
- `profile_id` (FK company_profiles)
- `topic_id` (FK topics)
- `eligibility_fit`
- `thematic_fit`
- `impact_fit`
- `implementation_fit`
- `consortium_fit`
- `data_ai_fit`
- `evidence_strength`
- `overall_fit`
- `gap_score`
- `readiness_score`
- `partner_dependency_score`
- `submission_priority`
- `confidence`
- `recommendation` (`go|watch|no_go`)
- `model_version`
- `generated_at`
- unique `(profile_id, topic_id, model_version)`

### `match_explanations_v2`
- `id`
- `match_result_id` (FK match_results_v2)
- `supporting_topic_sections` (JSON list)
- `supporting_profile_sections` (JSON list)
- `must_have_gaps` (JSON list)
- `nice_to_have_gaps` (JSON list)
- `suggested_partner_types` (JSON list)
- `suggested_actions` (JSON list)
- `why_fit` (JSON list)
- `why_not_fit` (JSON list)

## 4.2 Estensioni tabella `topics`
Aggiungere campi:
- `programme`, `destination`, `stage_type`, `opening_date`, `deadline_1`, `deadline_2`,
- `expected_contribution_min`, `expected_contribution_max`,
- `lump_sum`, `clinical_study_expected`, `ai_expected`, `data_requirements`, `ssh_required`,
- `eligibility_notes`, `restrictions`, `source_version`.

## 4.3 Tenancy/collaboration
- introdurre `organizations`, `organization_members`, `workspace_profiles`;
- migrare da sola chiave `user_id` a `(organization_id, workspace_id)` su workflow/report/match.

## 5) Matching engine V2

## 5.1 Pipeline a 4 livelli
1. Hard Filters
- action type compatibile;
- stage compatibility (single/two-stage);
- finestra deadline;
- TRL range;
- eligibility/geography;
- vincoli clinici/regolatori minimi.

2. Semantic Retrieval
- confronto sezione-sezione (capability<->scope, evidence<->expected outcomes, ecc.);
- top-k topic sections e top-k profile sections per evidenza.

3. Rubric Reranking (LLM con schema rigido)
- output JSON validato con campi numerici e liste gap/evidenze.

4. Decision layer
- calcolo `overall_fit`, `gap_score`, `readiness_score`, `partner_dependency_score`, `submission_priority`;
- recommendation finale `go/watch/no_go` + ruolo suggerito.

## 5.2 Rubrica JSON (contratto)
```json
{
  "eligibility_fit": 0,
  "thematic_fit": 0,
  "impact_fit": 0,
  "implementation_fit": 0,
  "consortium_fit": 0,
  "data_ai_fit": 0,
  "evidence_strength": 0,
  "overall_fit": 0,
  "must_have_gaps": [],
  "nice_to_have_gaps": [],
  "why_fit": [],
  "why_not_fit": [],
  "recommended_role": "coordinator|wp_leader|partner|watch_only",
  "confidence": 0
}
```

## 5.3 Formula base consigliata
- `overall_fit = 0.20*eligibility + 0.24*thematic + 0.16*impact + 0.14*implementation + 0.14*consortium + 0.12*evidence`
- applicare penalità deterministiche su must-have gap critici.

## 6) API backend V2

## 6.1 Nuovi endpoint
- `POST /api/v2/profiles/{id}/capabilities`
- `POST /api/v2/profiles/{id}/evidence`
- `POST /api/v2/matches/recompute`
- `GET /api/v2/matches?profile_id=&min_score=&recommendation=`
- `GET /api/v2/matches/{match_id}/explanation`
- `GET /api/v2/topics/{topic_id}/decision-card`
- `POST /api/v2/topics/compare`

## 6.2 Compatibilità
- mantenere endpoint v1 (`/api/topics`, `/api/profiles`, `/api/matches`) in read-only compatibile;
- frontend nuovo usa solo `/api/v2/...`;
- deprecazione v1 in 2 release.

## 7) Parsing & ingestion V2

## 7.1 Parser robusto
- mantenere parser regex attuale come fallback;
- aggiungere parser strutturato a "section detector" con strategie multiple (layout PDF, heading extraction, patterns UE);
- versionare parser (`parser_version`) per confrontare qualità nel tempo.

## 7.2 Enrichment
- taxonomy EU per cluster/destination/action type;
- normalizzazione sinonimi dominio (es. AI in health, RWD, EHDS, EOSC, FAIR, GDPR, SSH);
- tagging automatico su topic sections.

## 8) UI decisionale (frontend)

## 8.1 Dashboard
- `Opportunity Radar`: ranking per `submission_priority`;
- `Gap View`: must-have gap + partner types;
- `Trend View`: distribuzione destination/action/deadline.

## 8.2 Topic detail
- score card multidimensionale;
- evidenze pro/contro cliccabili;
- gap must-have/nice-to-have;
- ruolo consigliato;
- next actions con owner e target date.

Nota: eliminare scoring locale in `frontend/lib/fit.ts` e demandare al backend.

## 9) Sicurezza e platform hardening
- CORS restrittivo per ambienti prod;
- autenticazione forte (OIDC/SSO) + RBAC;
- audit trail su decisioni (`go/no-go`, note, approvazioni);
- isolamento dati per organization/workspace.

## 10) Piano di rollout (8 settimane)

### Sprint 1 (settimane 1-2)
- introdurre schema V2 (nuove tabelle + campi topic estesi);
- service layer `matching_v2_service.py` senza toccare v1;
- endpoint `/api/v2/matches/recompute` base (hard filters + retrieval preliminare).

Deliverable:
- migrazioni DB;
- test unit su hard filters;
- fixture di regressione scoring.

### Sprint 2 (settimane 3-4)
- implementare rubric reranking + structured outputs;
- salvare `match_results_v2` + `match_explanations_v2`;
- aggiungere endpoint explanation e decision-card.

Deliverable:
- contratti JSON validati;
- test integrazione con snapshot chiamate;
- fallback robusto se provider AI non disponibile.

### Sprint 3 (settimane 5-6)
- rifacimento frontend topic detail decisionale;
- dashboard radar/gap/trend;
- workflow multiutente (owner, stage, note, approvazione).

Deliverable:
- rimozione fit locale da frontend;
- UX decisionale completa;
- smoke test E2E.

### Sprint 4 (settimane 7-8)
- connectors estesi (Funding & Tenders + CORDIS enrichment);
- tuning pesi scoring per cluster;
- osservabilità (quality metrics, drift parser, hit@k retrieval).

Deliverable:
- report qualità matching;
- baseline KPI operativi;
- piano deprecazione v1.

## 11) KPI per misurare miglioramento
- Precision@10 shortlist topic;
- tasso di falsi positivi (topic con fit alto ma scartati in review umana);
- coverage explanation (% match con evidenze complete);
- tempo medio decisione go/no-go;
- stabilità parser (topic estratti correttamente per documento).

## 12) Backlog tecnico immediato (ordine pratico)
1. Spostare scoring decisionale 100% backend (stop scoring locale frontend).
2. Introdurre `topic_sections` e `profile_capabilities/evidence`.
3. Implementare hard filters come gate iniziale.
4. Aggiungere retrieval semantico sezione-sezione.
5. Aggiungere rubric JSON con explainability strutturata.
6. Rifare topic detail in chiave decisionale.
7. Integrare enrichment da fonti esterne per partner intelligence.

## 13) Rischi e mitigazioni
- Rischio: latenza LLM elevata.
  Mitigazione: retrieval stretto + batch asincrono + cache per match.

- Rischio: parser eterogeneo su PDF complessi.
  Mitigazione: parser multi-strategy + fallback regex + quality checks.

- Rischio: regressioni rispetto ai risultati attuali.
  Mitigazione: modalità dual-run v1/v2 e confronto score distribuzionale.

- Rischio: explainability non coerente.
  Mitigazione: schema rigido + validator server-side + test contract.

## 14) Primo incremento tecnico consigliato nel codice attuale
Intervenire subito su:
- nuovo modulo `backend/app/services/matching_v2_service.py`;
- nuovo modello `topic_sections` e pipeline ingest in `work_programme_pdf_service.py`;
- nuovo endpoint `/api/v2/matches/recompute` in `backend/app/api/routes.py`;
- disattivare progressivamente uso `frontend/lib/fit.ts` per decisioni.

