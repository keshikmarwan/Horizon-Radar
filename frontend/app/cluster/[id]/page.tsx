'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { FitConstellationLoader } from '@/components/FitConstellationLoader';
import {
  ClusterData,
  ClusterId,
  CLUSTERS,
  ClusterInstanceMeta,
  createClusterInstance,
  deleteClusterInstance,
  defaultInstanceName,
  ensureClusterWorkspace,
  listClusterInstances,
  renameClusterInstance,
  switchClusterInstance,
  writeClusterStore,
} from '@/lib/cluster-store';
import { apiGet, apiPost } from '@/lib/api';
import type { MatchRecomputeV2Response, MatchResultV2, TopicDecisionCardV2 } from '@/lib/types';

const CALL_VIEWER_KEY = 'horizon-radar-selected-call';
type ApiProfile = { id: number; name: string };
type ApiTopic = {
  id: number;
  topic_id: string;
  title: string;
  cluster: string | null;
  action_type: string | null;
  trl_min: number | null;
  trl_max: number | null;
  budget_total: number | null;
  deadline: string | null;
  status: string | null;
  topic_url: string | null;
  adjusted_score?: number | null;
  procedure_stage?: string | null;
  compliance_flags?: string[];
};

type FitSummary = {
  score: number;
  recommendation: 'GO' | 'WATCH' | 'NO-GO';
  explanation: string[];
  gaps: string[];
  semanticScore: number;
  keywordScore: number;
};

type TopicDecisionCardPreview = {
  topicTitle: string;
  topicText: string;
  summary: string;
  deadline: string | null;
  score: number;
  recommendation: string;
  overallFit: number;
  gapScore: number;
  readinessScore: number;
  partnerDependencyScore: number;
  submissionPriority: number;
  confidence: number;
  recommendedRole: string;
  whyFit: string[];
  whyNotFit: string[];
  mustHaveGaps: string[];
  niceToHaveGaps: string[];
  suggestedPartnerTypes: string[];
  suggestedActions: string[];
};

const FIT_MODEL_VERSION = 'v2-groq-fit';
const FIT_OVERLAY_MIN_AFTER_OUTCOME_MS = 15000;
const FIT_STREAM_EVENT = 'horizon-fit-stream';

type FitStreamTopic = { id: number; score: number; recommendation: string };
type FitStreamPayload = {
  active: boolean;
  stage: string;
  title: string;
  lines: string[];
  topics?: FitStreamTopic[];
};

function pushFitStream(payload: FitStreamPayload) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(FIT_STREAM_EVENT, { detail: payload }));
}

function formatError(err: unknown): string {
  if (err instanceof Error) return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

export default function ClusterPage() {
  const params = useParams<{ id: string }>();
  const clusterId = (params.id || '').toUpperCase() as ClusterId;

  const [clusterData, setClusterData] = useState<Partial<Record<ClusterId, ClusterData>>>({});
  const [instances, setInstances] = useState<ClusterInstanceMeta[]>([]);
  const [activeInstanceId, setActiveInstanceId] = useState('');
  const [isHydrated, setIsHydrated] = useState(false);
  const [fit, setFit] = useState<FitSummary | null>(null);
  const [topicFits, setTopicFits] = useState<TopicDecisionCardPreview[]>([]);
  const [fitStarted, setFitStarted] = useState(false);
  const [fitLoading, setFitLoading] = useState(false);
  const [fitBooting, setFitBooting] = useState(false);
  const [fitFinishing, setFitFinishing] = useState(false);
  const [fitClosing, setFitClosing] = useState(false);
  const [fitClosingExit, setFitClosingExit] = useState(false);
  const [fitError, setFitError] = useState('');
  const loaderPhase = fitFinishing || fitClosing || fitClosingExit ? 'finishing' : fitBooting ? 'booting' : 'running';

  const cluster = clusterData[clusterId];
  const validCluster = CLUSTERS.includes(clusterId);
  const activeInstance = instances.find((x) => x.id === activeInstanceId) || null;

  useEffect(() => {
    const ctx = ensureClusterWorkspace();
    setActiveInstanceId(ctx.instanceId);
    setInstances(ctx.instances);
    setClusterData(ctx.store.clusterData);
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated || !activeInstanceId) return;
    writeClusterStore({ clusterData }, activeInstanceId);
    setInstances(listClusterInstances());
  }, [clusterData, isHydrated, activeInstanceId]);

  useEffect(() => {
    if (!cluster) {
      setFit(null);
      setTopicFits([]);
      setFitError('');
    }
  }, [cluster]);

  useEffect(() => () => {
    pushFitStream({ active: false, stage: 'idle', title: '', lines: [] });
  }, []);

  const canFit = useMemo(() => {
    if (!cluster) return false;
    return (
      cluster.fileText.trim().length > 0 &&
      cluster.companyDescription.trim().length > 20 &&
      cluster.clusterInterests.trim().length > 5
    );
  }, [cluster]);

  const askInstanceName = (prefill?: string) => {
    const value = window.prompt('Nome istanza', prefill || defaultInstanceName());
    return value?.trim() || null;
  };

  const saveInstance = () => {
    if (!activeInstanceId) return;
    const name = askInstanceName(activeInstance?.name || defaultInstanceName());
    if (!name) return;
    writeClusterStore({ clusterData }, activeInstanceId);
    renameClusterInstance(activeInstanceId, name);
    setInstances(listClusterInstances());
  };

  const saveAndCreateNewInstance = () => {
    if (!activeInstanceId) return;
    const currentName = askInstanceName(activeInstance?.name || defaultInstanceName());
    if (!currentName) return;
    writeClusterStore({ clusterData }, activeInstanceId);
    renameClusterInstance(activeInstanceId, currentName);

    const newName = askInstanceName(defaultInstanceName());
    if (!newName) return;
    const created = createClusterInstance(newName);
    setActiveInstanceId(created.instanceId);
    setClusterData(created.store.clusterData);
    setFit(null);
    setTopicFits([]);
    setFitStarted(false);
    setInstances(listClusterInstances());
  };

  const onChangeInstance = (instanceId: string) => {
    setActiveInstanceId(instanceId);
    const store = switchClusterInstance(instanceId);
    setClusterData(store.clusterData);
    setFit(null);
    setTopicFits([]);
    setFitStarted(false);
    setInstances(listClusterInstances());
  };

  const onDeleteInstance = () => {
    if (!activeInstanceId) return;
    const ok = window.confirm(`Eliminare l'istanza "${activeInstance?.name || activeInstanceId}"?`);
    if (!ok) return;
    const result = deleteClusterInstance(activeInstanceId);
    setActiveInstanceId(result.instanceId);
    setClusterData(result.store.clusterData);
    setFit(null);
    setTopicFits([]);
    setFitStarted(false);
    setInstances(result.instances);
  };

  const updateField = (field: 'companyDescription' | 'clusterInterests', value: string) => {
    setClusterData((prev) => {
      const current = prev[clusterId];
      if (!current) return prev;
      return { ...prev, [clusterId]: { ...current, [field]: value } };
    });
  };

  const removeClusterFile = () => {
    if (!cluster || !cluster.fileName) return;
    const ok = window.confirm(`Rimuovere il file caricato per ${clusterId}?`);
    if (!ok) return;

    setClusterData((prev) => {
      const current = prev[clusterId];
      if (!current) return prev;
      return {
        ...prev,
        [clusterId]: {
          ...current,
          fileName: '',
          fileType: '',
          uploadedAt: '',
          fileText: '',
          extractedBy: '',
          extractedChars: 0,
          extractionError: '',
        },
      };
    });
    setFit(null);
    setTopicFits([]);
    setFitStarted(false);
    setFitError('');
    setFitLoading(false);
    setFitBooting(false);
    setFitFinishing(false);
    setFitClosing(false);
    setFitClosingExit(false);
  };

  const openCallViewer = (topic: TopicDecisionCardPreview, index: number) => {
    const payload = { clusterId, rank: index + 1, topic, generatedAt: new Date().toISOString() };
    localStorage.setItem(CALL_VIEWER_KEY, JSON.stringify(payload));
    window.open('/call-viewer', '_blank', 'noopener,noreferrer');
  };

  const tokenizeInterests = (text: string): string[] =>
    text
      .toLowerCase()
      .split(/[\n,;|]+/)
      .map((x) => x.trim())
      .filter((x) => x.length >= 3)
      .slice(0, 24);

  const runBackendFit = async () => {
    if (!cluster || !canFit) return;
    let outcomeReadyTs: number | null = null;
    let hasOutcome = false;
    setFitStarted(true);
    setFitBooting(true);
    setFitFinishing(false);
    setFitClosing(false);
    setFitClosingExit(false);
    setFitLoading(true);
    setFitError('');
    pushFitStream({
      active: true,
      stage: 'boot',
      title: 'Avvio Fit',
      lines: ['Inizializzo pipeline e verifico backend...'],
    });
    const bootTimer = window.setTimeout(() => setFitBooting(false), 950);

    try {
      await apiGet<{ status: string }>('/api/health');
      pushFitStream({
        active: true,
        stage: 'profile',
        title: 'Profilo',
        lines: ['Backend online.', 'Creo profilo workspace per il fit...'],
      });
      const tags = tokenizeInterests(cluster.clusterInterests);
      const createdProfile = await apiPost<ApiProfile>('/api/profiles', {
        user_id: 'frontend',
        name: `${clusterId} Workspace ${new Date().toLocaleDateString('it-IT')}`,
        description: cluster.companyDescription,
        tags,
        constraints: {
          must_have_keywords: tags.slice(0, 18),
        },
      });

      await apiPost('/api/ingest/work-programme-text', {
        text: cluster.fileText || '',
        cluster: clusterId,
        profile_id: createdProfile.id,
      });
      pushFitStream({
        active: true,
        stage: 'ingest',
        title: 'Ingestione',
        lines: [
          `Profilo #${createdProfile.id} creato.`,
          `Work Programme acquisito (${cluster.fileText.length} caratteri).`,
          'Invio a Groq per scoring fit...',
        ],
      });

      const recompute = await apiPost<MatchRecomputeV2Response>('/api/v2/matches/recompute', {
        profile_id: createdProfile.id,
        model_version: FIT_MODEL_VERSION,
        limit_topics: 600,
      });
      pushFitStream({
        active: true,
        stage: 'recompute',
        title: 'Scoring Server',
        lines: [
          `Topic valutati: ${recompute.evaluated_topics}`,
          `Match prodotti: ${recompute.matches_inserted}`,
          `Scartati da hard filter: ${recompute.matches_skipped_by_hard_filters}`,
          recompute.groq_coverage_total && recompute.groq_coverage_count !== undefined
            ? `Groq coverage: ${recompute.groq_coverage_count}/${recompute.groq_coverage_total}${recompute.groq_coverage_pct != null ? ` (${Math.round(recompute.groq_coverage_pct)}%)` : ''}`
            : 'Groq coverage: n/d',
        ],
        topics: (recompute.top_topics || []).slice(0, 4).map((t) => ({
          id: t.topic_db_id,
          score: Math.round(t.overall_fit),
          recommendation: t.recommendation.toUpperCase(),
        })),
      });

      const [topics, matches] = await Promise.all([
        apiGet<ApiTopic[]>(`/api/topics?cluster=${encodeURIComponent(clusterId)}`),
        apiGet<MatchResultV2[]>(`/api/v2/profiles/${createdProfile.id}/matches?model_version=${encodeURIComponent(FIT_MODEL_VERSION)}&limit=20`),
      ]);
      pushFitStream({
        active: true,
        stage: 'ranking',
        title: 'Ranking',
        lines: [
          `Topic nel cluster: ${topics.length}`,
          `Match caricati: ${matches.length}`,
          'Costruisco le schede decisione...',
        ],
      });

      const matchByTopicId = new Map<number, MatchResultV2>();
      for (const m of matches) matchByTopicId.set(m.topic_id, m);

      const ranked = topics
        .map((topic) => ({ topic, match: matchByTopicId.get(topic.id) || null }))
        .filter((row) => row.match)
        .sort((a, b) => (b.match?.submission_priority ?? 0) - (a.match?.submission_priority ?? 0))
        .slice(0, 20);

      const mapped: TopicDecisionCardPreview[] = await Promise.all(
        ranked.map(async ({ topic, match }) => {
          const card = await apiGet<TopicDecisionCardV2>(
            `/api/v2/topics/${topic.id}/decision-card?profile_id=${createdProfile.id}&model_version=${encodeURIComponent(FIT_MODEL_VERSION)}`
          );
          const summary = `ID: ${topic.topic_id}${topic.action_type ? ` • ${topic.action_type}` : ''}${
            topic.deadline ? ` • deadline ${new Date(topic.deadline).toLocaleDateString('it-IT')}` : ''
          }${topic.procedure_stage ? ` • ${topic.procedure_stage}` : ''}`;
          return {
            topicTitle: topic.title,
            topicText: [
              summary,
              ...(card.why_fit || []),
              ...(card.why_not_fit || []),
              ...(card.must_have_gaps || []),
              ...(card.suggested_actions || []),
            ].join('\n'),
            summary,
            deadline: topic.deadline,
            score: Math.round(card.overall_fit),
            recommendation: card.recommendation.toUpperCase(),
            overallFit: card.overall_fit,
            gapScore: card.gap_score,
            readinessScore: card.readiness_score,
            partnerDependencyScore: card.partner_dependency_score,
            submissionPriority: card.submission_priority,
            confidence: card.confidence,
            recommendedRole: card.recommended_role,
            whyFit: card.why_fit || [],
            whyNotFit: card.why_not_fit || [],
            mustHaveGaps: card.must_have_gaps || [],
            niceToHaveGaps: card.nice_to_have_gaps || [],
            suggestedPartnerTypes: card.suggested_partner_types || [],
            suggestedActions: card.suggested_actions || [],
          };
        })
      );
      setTopicFits(mapped);

      const avg = mapped.length > 0 ? Math.round(mapped.reduce((sum, r) => sum + r.overallFit, 0) / mapped.length) : 0;
      const recommendation = avg >= 55 ? 'GO' : avg >= 30 ? 'WATCH' : 'NO-GO';
      setFit({
        score: avg,
        recommendation,
        explanation: [
          `Fit calcolato su ${mapped.length} topic ufficiali del Work Programme.`,
          `Metodo V2-Groq: hard filters + retrieval semantico + scoring e razionale guidati da Groq.`,
        ],
        gaps: mapped.flatMap((m) => m.mustHaveGaps).slice(0, 8),
        semanticScore: avg,
        keywordScore: avg,
      });
      hasOutcome = true;
      outcomeReadyTs = Date.now();
      pushFitStream({
        active: true,
        stage: 'done',
        title: 'Fit Completato',
        lines: [
          `Fit score cluster: ${avg}/100`,
          `Raccomandazione: ${recommendation}`,
          `Top call elaborate: ${mapped.length}`,
        ],
        topics: mapped.slice(0, 4).map((m, idx) => ({
          id: idx + 1,
          score: Math.round(m.overallFit),
          recommendation: m.recommendation,
        })),
      });

      if (mapped.length === 0) {
        setFitError(
          cluster.fileText?.trim()
            ? 'Nessun topic utile trovato nel testo importato. Verifica che il documento contenga topic ID (es. HORIZON-HLTH-...).'
            : 'Nessun testo Work Programme trovato. Carica un PDF o incolla il testo prima di avviare il fit.'
        );
      }
    } catch (err) {
      setFit(null);
      setTopicFits([]);
      pushFitStream({
        active: true,
        stage: 'error',
        title: 'Errore Fit',
        lines: [formatError(err)],
      });
      setFitError(
        `Errore backend durante Avvia Fit V2: ${formatError(err)}. Controlla che backend sia attivo su http://127.0.0.1:8000.`
      );
    } finally {
      window.clearTimeout(bootTimer);
      if (hasOutcome && outcomeReadyTs) {
        const remainingMs = outcomeReadyTs + FIT_OVERLAY_MIN_AFTER_OUTCOME_MS - Date.now();
        if (remainingMs > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, remainingMs));
        }
      }
      if (hasOutcome) {
        setFitFinishing(true);
        await new Promise((resolve) => window.setTimeout(resolve, 1250));
        setFitFinishing(false);
        setFitClosing(true);
      } else {
        setFitLoading(false);
        setFitFinishing(false);
        setFitClosing(false);
        setFitBooting(false);
        pushFitStream({ active: false, stage: 'idle', title: '', lines: [] });
      }
    }
  };

  const onAcceptFitOutcome = () => {
    if (!fitClosing) return;
    setFitClosingExit(true);
    window.setTimeout(() => {
      setFitLoading(false);
      setFitClosing(false);
      setFitClosingExit(false);
      setFitBooting(false);
      pushFitStream({ active: false, stage: 'idle', title: '', lines: [] });
    }, 440);
  };

  const onOpenTopCallFromOutcome = () => {
    if (topicFits.length > 0) {
      openCallViewer(topicFits[0], 0);
    }
    onAcceptFitOutcome();
  };

  const onOpenReportFromOutcome = () => {
    window.open('/reports', '_blank', 'noopener,noreferrer');
    onAcceptFitOutcome();
  };

  const onRecomputeFromOutcome = () => {
    setFitClosingExit(true);
    window.setTimeout(() => {
      setFitLoading(false);
      setFitClosing(false);
      setFitClosingExit(false);
      setFitBooting(false);
      setFitFinishing(false);
      void runBackendFit();
    }, 260);
  };

  if (!validCluster) {
    return (
      <section>
        <h1>Cluster non valido</h1>
        <Link href="/">Torna alla home</Link>
      </section>
    );
  }

  if (!cluster) {
    return (
      <section>
        <h1>{clusterId}</h1>
        <div className="card">
          <h3>Istanze Workspace Call</h3>
          <div className="row">
            <button onClick={saveInstance}>Salva</button>
            <button onClick={saveAndCreateNewInstance}>Salva e nuova istanza</button>
            <button className="btn-danger" onClick={onDeleteInstance}>Elimina istanza</button>
            <select value={activeInstanceId} onChange={(e) => onChangeInstance(e.target.value)} style={{ minWidth: 300 }}>
              {instances.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.name} ({new Date(inst.updatedAt).toLocaleString()})
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="small">Nessun file caricato per questo cluster in questa istanza.</p>
        <Link href="/">Torna alla home e carica il file</Link>
      </section>
    );
  }

  return (
    <section>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>{clusterId} - Fit Workspace</h1>
        <Link href="/">Back to uploads</Link>
      </div>

      <div className="card">
        <h3>Istanze Workspace Call</h3>
        <div className="row">
          <button onClick={saveInstance}>Salva</button>
          <button onClick={saveAndCreateNewInstance}>Salva e nuova istanza</button>
          <button className="btn-danger" onClick={onDeleteInstance}>Elimina istanza</button>
          <select value={activeInstanceId} onChange={(e) => onChangeInstance(e.target.value)} style={{ minWidth: 300 }}>
            {instances.map((inst) => (
              <option key={inst.id} value={inst.id}>
                {inst.name} ({new Date(inst.updatedAt).toLocaleString()})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="card">
        <p><strong>File:</strong> {cluster.fileName}</p>
        <p className="small"><strong>Type:</strong> {cluster.fileType || 'unknown'}</p>
        <p className="small"><strong>Upload:</strong> {cluster.uploadedAt ? new Date(cluster.uploadedAt).toLocaleString() : 'n/d'}</p>
        {cluster.extractedBy ? <p className="small"><strong>Extract:</strong> {cluster.extractedBy} ({cluster.extractedChars || 0} chars)</p> : null}
        {cluster.extractionError ? <p className="small"><strong>Errore:</strong> {cluster.extractionError}</p> : null}
        {cluster.fileText ? (
          <p className="small">Testo estratto disponibile ({cluster.fileText.length} chars).</p>
        ) : (
          <p className="small">File senza testo estratto: il fit non puo essere affidabile.</p>
        )}
        {cluster.fileName ? (
          <div className="row" style={{ marginTop: '0.8rem' }}>
            <button className="btn-danger" onClick={removeClusterFile} type="button">
              Rimuovi file
            </button>
          </div>
        ) : null}
      </div>

      <div className="card">
        <h3>Profilo Azienda (per {clusterId})</h3>
        <label>Descrizione azienda (usata per semantic fit)</label>
        <textarea
          rows={6}
          style={{ width: '100%', marginTop: '0.5rem' }}
          placeholder="Descrivi competenze, tecnologie, track record, TRL target..."
          value={cluster.companyDescription}
          onChange={(e) => updateField('companyDescription', e.target.value)}
        />
        <label style={{ marginTop: '0.9rem', display: 'block' }}>Interessi cluster (usati per keyword fit)</label>
        <textarea
          rows={5}
          style={{ width: '100%', marginTop: '0.5rem' }}
          placeholder="Keyword, topic target, use case, constraints..."
          value={cluster.clusterInterests}
          onChange={(e) => updateField('clusterInterests', e.target.value)}
        />
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h3>Fit Analysis</h3>
          <button onClick={() => { void runBackendFit(); }} disabled={!canFit || fitLoading}>
            {fitLoading ? 'Calcolo in corso...' : 'Avvia Fit'}
          </button>
        </div>
        <p className="small">
          Metodo fit: parsing Work Programme + hard filters + retrieval semantico + scoring Groq (`{FIT_MODEL_VERSION}`).
        </p>
        {!fitStarted ? <p className="small">Premi "Avvia Fit" per estrarre call ufficiali e calcolare la classifica fit.</p> : null}
        {fitError ? <p className="small">{fitError}</p> : null}
      </div>

      <div className="card">
        <h3>Fit Analysis (Overall Cluster)</h3>
        {!canFit ? (
          <p className="small">Compila descrizione e interessi per attivare il fit.</p>
        ) : fit ? (
          <>
            <p><strong>Fit score:</strong> {fit.score}/100</p>
            <p><strong>Semantic score:</strong> {fit.semanticScore}/100</p>
            <p><strong>Keyword score:</strong> {fit.keywordScore}/100</p>
            <p><strong>Recommendation:</strong> <span className="score">{fit.recommendation}</span></p>
            <h4>Spiegazione</h4>
            <ul>{fit.explanation.map((line, idx) => <li key={idx}>{line}</li>)}</ul>
          </>
        ) : (
          <p className="small">Fit non disponibile.</p>
        )}
      </div>

      <div className="card">
        <h3>Top 20 Call (Schede)</h3>
        {!canFit ? (
          <p className="small">Compila descrizione/interessi per calcolare il ranking call.</p>
        ) : !fitStarted ? (
          <p className="small">Premi "Avvia Fit" per generare le call.</p>
        ) : topicFits.length === 0 ? (
          <p className="small">Nessuna call identificata nel file. Verifica che il testo estratto non sia vuoto.</p>
        ) : (
          <div className="row" style={{ alignItems: 'stretch' }}>
            {topicFits.map((t, idx) => (
              <article key={`${t.topicTitle}-${idx}`} className="card" style={{ flex: 1, minWidth: 320 }}>
                <h4>#{idx + 1} - {t.topicTitle.slice(0, 90)}</h4>
                <p><strong>Overall fit:</strong> {Math.round(t.overallFit)}/100</p>
                <p><strong>Gap:</strong> {Math.round(t.gapScore)}/100 | <strong>Readiness:</strong> {Math.round(t.readinessScore)}/100</p>
                <p><strong>Submission priority:</strong> {Math.round(t.submissionPriority)}/100 | <strong>Confidence:</strong> {Math.round(t.confidence)}/100</p>
                <p><strong>Recommendation:</strong> <span className="score">{t.recommendation}</span> | <strong>Role:</strong> {t.recommendedRole}</p>
                <p><strong>Riassunto:</strong> <span className="small">{t.summary || 'N/A'}</span></p>
                <p><strong>Must-have gaps:</strong> <span className="small">{t.mustHaveGaps.length > 0 ? t.mustHaveGaps.join(', ') : 'nessun gap critico'}</span></p>
                <p><strong>Partner suggeriti:</strong> <span className="small">{t.suggestedPartnerTypes.length > 0 ? t.suggestedPartnerTypes.join(', ') : 'n/d'}</span></p>
                <button onClick={() => openCallViewer(t, idx)}>Apri testo completo (nuova scheda)</button>
              </article>
            ))}
          </div>
        )}
      </div>

      {fitLoading ? (
        <div
          className={`fit-loading-overlay${fitBooting ? ' is-booting' : ''}${fitFinishing ? ' is-finishing' : ''}${fitClosingExit ? ' is-closing' : ''}`}
          aria-live="polite"
          aria-label="Fit loading animation"
        >
          <FitConstellationLoader phase={loaderPhase} />
          {fitClosing ? (
            fit ? (
              <div className="fit-outcome-card" role="status" aria-live="polite">
                <h4>Fit Outcome</h4>
                <p><strong>Score:</strong> {fit.score}/100</p>
                <p><strong>Recommendation:</strong> {fit.recommendation}</p>
                <p className="small">Top call valutate: {topicFits.length}</p>
                <div className="fit-outcome-actions">
                  <button onClick={onOpenTopCallFromOutcome}>Apri Top Call</button>
                  <button onClick={onOpenReportFromOutcome}>Apri Report</button>
                  <button onClick={onRecomputeFromOutcome}>Ricalcola</button>
                  <button onClick={onAcceptFitOutcome}>Continua</button>
                </div>
              </div>
            ) : null
          ) : null}
          <div className="fit-loading-label">
            {fitClosing
              ? 'Fit pronto. Apertura risultati...'
              : fitFinishing
                ? 'Fit completato. Consolidamento finale in corso...'
                : fitBooting
                  ? 'Inizializzo il motore di fit...'
                  : 'Analisi fit in corso...'}
          </div>
        </div>
      ) : null}
    </section>
  );
}
