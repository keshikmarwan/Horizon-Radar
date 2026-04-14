'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ChangeEvent, useEffect, useMemo, useState } from 'react';
import { FitConstellationLoader } from '@/components/FitConstellationLoader';
import {
  ClusterData,
  ClusterId,
  CLUSTERS,
  ensureClusterWorkspace,
  writeClusterStore,
} from '@/lib/cluster-store';
import { companyKey, readCrmStore } from '@/lib/crm-store';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';
import type {
  HorizonMatcherCallData,
  HorizonMatcherResponse,
  HorizonMatcherResult,
  HorizonMatcherScoreBreakdown,
  HorizonMatcherUploadResponse,
} from '@/lib/types';

// ── Cluster ID → cluster name (must match backend CLUSTER_TO_ID in routes.py)
const CLUSTER_TO_NAME: Record<string, string> = {
  CL1: 'Health',
  CL2: 'Digital',
  CL3: 'Security',
  CL4: 'Manufacturing',
  CL5: 'Climate',
  CL6: 'Food',
};

const TRL_LABELS: Record<number, string> = {
  1: 'TRL 1 — Principi osservati',
  2: 'TRL 2 — Concetto formulato',
  3: 'TRL 3 — Proof of concept',
  4: 'TRL 4 — Validato in laboratorio',
  5: 'TRL 5 — Validato in ambiente rilevante',
  6: 'TRL 6 — Demo in ambiente rilevante',
  7: 'TRL 7 — Demo in ambiente operativo',
  8: 'TRL 8 — Sistema completato e qualificato',
  9: 'TRL 9 — Deployment operativo',
};

// ── Types ────────────────────────────────────────────────────────────────────

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
  spiderAxes: Record<string, number>;
  scoreBreakdown: HorizonMatcherScoreBreakdown;
  callData: HorizonMatcherCallData | null;
};

type ProfileOption = {
  id: string;
  name: string;
  description: string;
  keywords: string[];
};

const FIT_OVERLAY_MIN_AFTER_OUTCOME_MS = 2000;
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
  try { return JSON.stringify(err); } catch { return String(err); }
}

function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)); }

function mapMatcherResultToPreview(row: HorizonMatcherResult): TopicDecisionCardPreview {
  const r = Math.round(row.reliability_score * 100);
  const sem = Math.round((row.score_breakdown.semantic_score || 0) * 100);
  const bm = Math.round((row.score_breakdown.bm25_score || 0) * 100);
  const con = Math.round((row.score_breakdown.constraints_score || 0) * 100);
  const trl = Math.round((row.score_breakdown.trl_score || 0) * 100);
  const gaps: string[] = [];
  if (trl < 60) gaps.push('TRL gap da verificare');
  if (con < 50) gaps.push('Vincoli/eligibility deboli');
  if (!row.score_breakdown.bm25_boost_applied) gaps.push('Nessun boost keyword UE');
  return {
    topicTitle: `${row.call_id} — ${row.title}`,
    topicText: row.justification,
    summary: `${row.cluster || ''}${row.type_of_action ? ` · ${row.type_of_action}` : ''}`,
    deadline: row.call_data?.deadline ?? null,
    score: r,
    recommendation: r >= 55 ? 'GO' : r >= 30 ? 'WATCH' : 'NO-GO',
    overallFit: r,
    gapScore: 100 - con,
    readinessScore: sem,
    partnerDependencyScore: bm,
    submissionPriority: r,
    confidence: clamp(Math.round(100 - Math.abs(sem - bm) * 0.6), 35, 96),
    recommendedRole: row.type_of_action || 'N/A',
    whyFit: [row.justification],
    whyNotFit: [],
    mustHaveGaps: gaps,
    niceToHaveGaps: [],
    suggestedPartnerTypes: [],
    suggestedActions: ['Verifica readiness consorzio', 'Controlla requisiti specifici nel testo'],
    spiderAxes: row.spider_axes || {},
    scoreBreakdown: row.score_breakdown,
    callData: row.call_data ?? null,
  };
}

// ── Design system components ─────────────────────────────────────────────────

function RecommendationBadge({ value }: { value: string }) {
  const cls = value === 'GO'
    ? 'fit-badge fit-badge--go'
    : value === 'WATCH' ? 'fit-badge fit-badge--watch' : 'fit-badge fit-badge--nogo';
  return <span className={cls}>{value}</span>;
}

function ScoreRing({ value, label }: { value: number; label: string }) {
  const r = 26, circ = 2 * Math.PI * r, dash = (value / 100) * circ;
  return (
    <div className="fit-score-ring">
      <svg viewBox="0 0 68 68" className="fit-score-ring-svg" aria-hidden>
        <circle cx="34" cy="34" r={r} className="fit-score-ring-track" />
        <circle cx="34" cy="34" r={r} className="fit-score-ring-fill"
          strokeDasharray={`${dash} ${circ}`} strokeDashoffset={circ / 4} />
      </svg>
      <div className="fit-score-ring-inner">
        <span className="fit-score-ring-value">{value}</span>
      </div>
      <span className="fit-score-ring-label">{label}</span>
    </div>
  );
}

// Mini spider (card grids)
function SpiderMini({ axes }: { axes: Record<string, number> }) {
  const defs = [
    { key: 'trl_alignment', label: 'TRL' },
    { key: 'impact_policy', label: 'Impatto' },
    { key: 'scope_methodology', label: 'Metodo' },
    { key: 'consortium_stakeholders', label: 'Consorzio' },
    { key: 'fair_compliance', label: 'FAIR' },
    { key: 'inclusion_ethics', label: 'Etica' },
  ];
  const cx = 74, cy = 74, outer = 54;
  const pts = defs.map(({ key }, i) => {
    const v = clamp(((axes[key] ?? 1) - 1) / 4, 0, 1);
    const a = -Math.PI / 2 + i * 2 * Math.PI / defs.length;
    return `${cx + Math.cos(a) * outer * v},${cy + Math.sin(a) * outer * v}`;
  }).join(' ');
  return (
    <svg viewBox="0 0 148 148" className="pipeline-spider" role="img" aria-label="Spider chart">
      {[0.25, 0.5, 0.75, 1].map((ratio, idx) => (
        <polygon key={idx} points={defs.map((_, i) => {
          const a = -Math.PI / 2 + i * 2 * Math.PI / defs.length;
          return `${cx + Math.cos(a) * outer * ratio},${cy + Math.sin(a) * outer * ratio}`;
        }).join(' ')} className="pipeline-spider-grid" />
      ))}
      {defs.map(({ key, label }, i) => {
        const a = -Math.PI / 2 + i * 2 * Math.PI / defs.length;
        return (
          <g key={key}>
            <line x1={cx} y1={cy} x2={cx + Math.cos(a) * outer} y2={cy + Math.sin(a) * outer} className="pipeline-spider-axis" />
            <text x={cx + Math.cos(a) * (outer + 12)} y={cy + Math.sin(a) * (outer + 12)} className="pipeline-spider-label" textAnchor="middle" dominantBaseline="middle">{label}</text>
          </g>
        );
      })}
      <polygon points={pts} className="pipeline-spider-fill" />
      <polygon points={pts} className="pipeline-spider-stroke" />
    </svg>
  );
}

// Full spider (detail view) — larger, with value labels on each axis
function SpiderFull({ axes }: { axes: Record<string, number> }) {
  const defs = [
    { key: 'trl_alignment', label: 'Maturità TRL' },
    { key: 'impact_policy', label: 'Impatto Politico' },
    { key: 'scope_methodology', label: 'Metodologia' },
    { key: 'consortium_stakeholders', label: 'Consorzio' },
    { key: 'fair_compliance', label: 'FAIR' },
    { key: 'inclusion_ethics', label: 'Etica/Inclusione' },
  ];
  const cx = 130, cy = 130, outer = 100;
  const pts = defs.map(({ key }, i) => {
    const v = clamp(((axes[key] ?? 1) - 1) / 4, 0, 1);
    const a = -Math.PI / 2 + i * 2 * Math.PI / defs.length;
    return `${cx + Math.cos(a) * outer * v},${cy + Math.sin(a) * outer * v}`;
  }).join(' ');
  return (
    <svg viewBox="0 0 260 260" className="spider-full" role="img" aria-label="Spider chart dettagliato">
      {[0.25, 0.5, 0.75, 1].map((ratio, idx) => (
        <polygon key={idx} points={defs.map((_, i) => {
          const a = -Math.PI / 2 + i * 2 * Math.PI / defs.length;
          return `${cx + Math.cos(a) * outer * ratio},${cy + Math.sin(a) * outer * ratio}`;
        }).join(' ')} className="pipeline-spider-grid" />
      ))}
      {/* Scale labels at 1, 2, 3, 4, 5 on first axis */}
      {[0.25, 0.5, 0.75, 1].map((ratio, idx) => {
        const a = -Math.PI / 2;
        const val = idx + 2;
        return (
          <text key={idx} x={cx + Math.cos(a) * outer * ratio - 6} y={cy + Math.sin(a) * outer * ratio - 4}
            className="spider-full-scale" textAnchor="middle">{val}</text>
        );
      })}
      {defs.map(({ key, label }, i) => {
        const a = -Math.PI / 2 + i * 2 * Math.PI / defs.length;
        const val = (axes[key] ?? 1).toFixed(1);
        const labelR = outer + 22;
        return (
          <g key={key}>
            <line x1={cx} y1={cy} x2={cx + Math.cos(a) * outer} y2={cy + Math.sin(a) * outer}
              className="pipeline-spider-axis" />
            <text x={cx + Math.cos(a) * labelR} y={cy + Math.sin(a) * labelR}
              className="spider-full-label" textAnchor="middle" dominantBaseline="middle">{label}</text>
            <text x={cx + Math.cos(a) * outer * 0.55} y={cy + Math.sin(a) * outer * 0.55}
              className="spider-full-val" textAnchor="middle" dominantBaseline="middle">{val}</text>
          </g>
        );
      })}
      <polygon points={pts} className="pipeline-spider-fill" />
      <polygon points={pts} className="pipeline-spider-stroke" />
    </svg>
  );
}

// Score breakdown — shows weight contribution of each component
function ScoreBreakdown({ breakdown }: { breakdown: HorizonMatcherScoreBreakdown }) {
  const wSemantic = (breakdown.weights_used?.semantic ?? 0.5) * 100;
  const wBm25 = (breakdown.weights_used?.bm25 ?? 0.3) * 100;
  const wConstraints = (breakdown.weights_used?.constraints ?? 0.2) * 100;
  const rows = [
    { label: 'Impact Match (A1)', key: 'impact_match' as const, weight: Math.round(wSemantic / 2), desc: 'Missione aziendale vs Expected Outcomes (semantica)' },
    { label: 'Technical Match (A2)', key: 'technical_match' as const, weight: Math.round(wSemantic / 2), desc: 'Know-how tecnico vs Scope della call (semantica)' },
    { label: 'BM25 Keyword', key: 'bm25_score' as const, weight: Math.round(wBm25), desc: 'Overlap keyword con vocabolario tecnico UE' },
    { label: 'Vincoli Tecnici', key: 'constraints_score' as const, weight: Math.round(wConstraints), desc: 'TRL delta + bonus eligibility (SME, SSH, FAIR, Gender)' },
  ];
  return (
    <div className="fit-breakdown">
      <h5 className="fit-breakdown-title">Come è stato calcolato</h5>
      {rows.map(row => {
        const val = breakdown[row.key] as number;
        const pct = Math.round(val * 100);
        return (
          <div key={row.key} className="fit-breakdown-row">
            <div className="fit-breakdown-meta">
              <span className="fit-breakdown-name">{row.label}</span>
              <span className="fit-breakdown-weight">peso {row.weight}%</span>
              <span className="fit-breakdown-pct">{pct}%</span>
            </div>
            <div className="fit-breakdown-bar-track">
              <div className="fit-breakdown-bar-fill" style={{ width: `${pct}%` }} />
            </div>
            <p className="fit-breakdown-desc">{row.desc}</p>
          </div>
        );
      })}
      <div className="fit-breakdown-footer">
        {breakdown.bm25_boost_applied && <span className="fit-breakdown-boost">✦ Boost keyword UE attivo (+15%)</span>}
        <span>
          TRL score: {Math.round(breakdown.trl_score * 100)}% · Eligibility: {Math.round(breakdown.eligibility_score * 100)}%
          {breakdown.weighted_contributions?.total !== undefined
            ? ` · Totale pesato: ${Math.round((breakdown.weighted_contributions.total || 0) * 100)}%`
            : ''}
        </span>
      </div>
    </div>
  );
}

// Consortium suggestions — matches CRM contacts to the call based on tags/roles
function ConsortiumSuggestions({ callText, callTitle }: { callText: string; callTitle: string }) {
  const crm = readCrmStore();
  const tagById = new Map(crm.tags.map(t => [t.id, t]));
  const searchText = (callTitle + ' ' + callText).toLowerCase();

  const scored = crm.contacts
    .map(contact => {
      let score = 0;
      const reasons: string[] = [];
      const contactTags = contact.subTagIds
        .map(id => tagById.get(id)?.label || '')
        .filter(Boolean);
      const companyTags = (crm.companyTagIds[companyKey(contact.company)] || [])
        .map(id => tagById.get(id)?.label || '')
        .filter(Boolean);
      const allTags = [...new Set([...contactTags, ...companyTags])];

      for (const tag of allTags) {
        if (searchText.includes(tag.toLowerCase())) {
          score += 2;
          reasons.push(tag);
        }
      }
      if (contact.role && searchText.includes(contact.role.toLowerCase())) {
        score += 3;
        reasons.push(contact.role);
      }
      return { contact, score, reasons: [...new Set(reasons)].slice(0, 3) };
    })
    .filter(x => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);

  if (scored.length === 0) {
    return (
      <p className="fit-hint">
        Nessun contatto CRM rilevante trovato. Aggiungi contatti con tag pertinenti alla call.
      </p>
    );
  }

  return (
    <div className="fit-consortium-list">
      {scored.map(({ contact, score, reasons }) => (
        <div key={contact.id} className="fit-consortium-contact">
          <div className="fit-consortium-contact-main">
            <span className="fit-consortium-name">{contact.firstName} {contact.lastName}</span>
            {contact.company && <span className="fit-consortium-company">{contact.company}</span>}
            {contact.role && <span className="fit-consortium-role">{contact.role}</span>}
          </div>
          {reasons.length > 0 && (
            <div className="fit-consortium-tags">
              {reasons.map(r => <span key={r} className="fit-consortium-tag">{r}</span>)}
            </div>
          )}
          <span className="fit-consortium-score">match: {score}</span>
        </div>
      ))}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function FitPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const clusterId = (params.id || '').toUpperCase() as ClusterId;

  const [clusterData, setClusterData] = useState<Partial<Record<ClusterId, ClusterData>>>({});
  const [isHydrated, setIsHydrated] = useState(false);
  const [fit, setFit] = useState<FitSummary | null>(null);
  const [topicFits, setTopicFits] = useState<TopicDecisionCardPreview[]>([]);
  const [otherTopicFits, setOtherTopicFits] = useState<TopicDecisionCardPreview[]>([]);
  const [matcherStatus, setMatcherStatus] = useState<{ calls_json?: boolean; index_faiss?: boolean; metadata_json?: boolean; qa_report_json?: boolean } | null>(null);
  const [uploadMessage, setUploadMessage] = useState('');
  const [uploading, setUploading] = useState(false);
  const [profileOptions, setProfileOptions] = useState<ProfileOption[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [selectedProfileId, setSelectedProfileId] = useState('');
  const [selectedTopic, setSelectedTopic] = useState<{ topic: TopicDecisionCardPreview; rank: number } | null>(null);
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
  const matcherReady = Boolean(matcherStatus?.calls_json && matcherStatus?.index_faiss && matcherStatus?.metadata_json);

  const profileChoices = useMemo<ProfileOption[]>(() => {
    const kw = (cluster?.clusterInterests || '').split(/[\n,;|]+/).map(x => x.trim()).filter(x => x.length >= 2).slice(0, 24);
    return [
      { id: 'manual:current', name: 'Profilo corrente (manuale)', description: cluster?.companyDescription || '', keywords: kw },
      ...profileOptions,
    ];
  }, [cluster?.companyDescription, cluster?.clusterInterests, profileOptions]);

  useEffect(() => {
    const store = ensureClusterWorkspace();
    if (!store.clusterData[clusterId]) {
      store.clusterData[clusterId] = {
        fileName: '', fileType: '', uploadedAt: '', fileText: '',
        extractedBy: '', extractedChars: 0, extractionError: '',
        companyDescription: '', clusterInterests: '',
        trlCurrent: 5, isSme: false, sshCapacity: false,
        fairCompliant: false, genderDimensionActive: false,
      };
      writeClusterStore(store);
    }
    setClusterData(store.clusterData);
    setIsHydrated(true);
  }, [clusterId]);

  useEffect(() => { if (isHydrated) writeClusterStore({ clusterData }); }, [clusterData, isHydrated]);
  useEffect(() => { if (!cluster) { setFit(null); setTopicFits([]); setOtherTopicFits([]); setSelectedTopic(null); setFitError(''); } }, [cluster]);
  useEffect(() => {
    apiGet<{ calls_json?: boolean; index_faiss?: boolean; metadata_json?: boolean; qa_report_json?: boolean }>('/api/horizon-matcher/status')
      .then(setMatcherStatus)
      .catch(err => setFitError(`Matcher non disponibile: ${formatError(err)}`));
  }, []);

  // Generic field updater for ClusterData
  function updateClusterField<K extends keyof ClusterData>(field: K, value: ClusterData[K]) {
    setClusterData(prev => {
      const c = prev[clusterId];
      return c ? { ...prev, [clusterId]: { ...c, [field]: value } } : prev;
    });
  }

  const refreshProfiles = async () => {
    setProfilesLoading(true);
    const out: ProfileOption[] = [];
    try {
      const crm = readCrmStore();
      const tagById = new Map(crm.tags.map(t => [t.id, t]));
      const byCompany = new Map<string, typeof crm.contacts>();
      for (const c of crm.contacts) {
        const k = companyKey(c.company);
        if (k) byCompany.set(k, [...(byCompany.get(k) || []), c]);
      }
      for (const [k, contacts] of byCompany.entries()) {
        const name = contacts[0]?.company?.trim() || k;
        const kw = [...new Set([
          ...(crm.companyTagIds[k] || []).map(id => tagById.get(id)?.label || ''),
          ...contacts.flatMap(c => c.subTagIds || []).map(id => tagById.get(id)?.label || ''),
          ...contacts.map(c => c.role?.trim() || ''),
        ])].filter(x => x.length > 1).slice(0, 24);
        out.push({ id: `crm:${k}`, name, description: `Azienda: ${name}`, keywords: kw });
      }
    } catch { /* ignore */ }
    setProfileOptions(
      out.filter((x, i, a) => a.findIndex(o => o.name.toLowerCase() === x.name.toLowerCase()) === i)
    );
    setProfilesLoading(false);
  };

  useEffect(() => { void refreshProfiles(); }, []);
  useEffect(() => {
    if (!selectedProfileId || !profileChoices.some(p => p.id === selectedProfileId))
      setSelectedProfileId(profileChoices[0]?.id || '');
  }, [selectedProfileId, profileChoices]);
  useEffect(() => () => { pushFitStream({ active: false, stage: 'idle', title: '', lines: [] }); }, []);

  const canFit = useMemo(() =>
    Boolean(cluster && cluster.companyDescription.trim().length > 20 && cluster.clusterInterests.trim().length > 5 && matcherReady),
    [cluster, matcherReady]
  );

  const removeFile = () => {
    if (!cluster?.fileName || !window.confirm('Rimuovere il file caricato?')) return;
    setClusterData(prev => {
      const c = prev[clusterId];
      return c ? { ...prev, [clusterId]: { ...c, fileName: '', fileType: '', uploadedAt: '', fileText: '', extractedBy: '', extractedChars: 0, extractionError: '' } } : prev;
    });
    setFit(null); setTopicFits([]); setOtherTopicFits([]); setSelectedTopic(null);
    setFitStarted(false); setFitError(''); setFitLoading(false);
    setFitBooting(false); setFitFinishing(false); setFitClosing(false); setFitClosingExit(false);
  };

  const openTopicDetail = (topic: TopicDecisionCardPreview, idx: number) => {
    setSelectedTopic({ topic, rank: idx + 1 });
    window.setTimeout(() => document.getElementById('fit-selected-call')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  };

  const tokenize = (t: string) =>
    t.toLowerCase().split(/[\n,;|]+/).map(x => x.trim()).filter(x => x.length >= 3).slice(0, 24);

  const onUploadPdf = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true); setUploadMessage(''); setFitError('');
    try {
      const fd = new FormData();
      const multiUpload = files.length > 1;
      if (multiUpload) {
        files.forEach(file => fd.append('files', file));
      } else {
        fd.append('file', files[0]);
      }
      const up = await apiPostFormData<HorizonMatcherUploadResponse>(
        multiUpload ? '/api/horizon-matcher/upload-pdfs' : '/api/horizon-matcher/upload-pdf',
        fd
      );
      const suggested = (up.suggested_cluster_id || '').toUpperCase() as ClusterId;
      const target = !multiUpload && CLUSTERS.includes(suggested) ? suggested : clusterId;
      setMatcherStatus(up.status as { calls_json?: boolean; index_faiss?: boolean; metadata_json?: boolean; qa_report_json?: boolean });
      const filesProcessed = up.files_processed ?? files.length;
      const anomalyCounts = (up.quality_summary?.anomaly_counts || {}) as Record<string, number>;
      const dirtyCount = (anomalyCounts.expected_outcomes_contains_scope || 0) + (anomalyCounts.scope_contains_destination || 0);
      setUploadMessage(
        `${up.filename} — ${up.calls_parsed} call` +
        `${filesProcessed > 1 ? ` · ${filesProcessed} file` : ''}` +
        `${up.detected_cluster ? ` · ${up.detected_cluster}` : ''}` +
        `${dirtyCount > 0 ? ` · ${dirtyCount} anomalie parser da rivedere` : ''}`
      );
      setClusterData(prev => {
        const empty: ClusterData = {
          fileName: '', fileType: '', uploadedAt: '', fileText: '',
          extractedBy: '', extractedChars: 0, extractionError: '',
          companyDescription: '', clusterInterests: '',
          trlCurrent: 5, isSme: false, sshCapacity: false,
          fairCompliant: false, genderDimensionActive: false,
        };
        return {
          ...prev,
          [target]: {
            ...(prev[target] ?? prev[clusterId] ?? empty),
            fileName: files.length === 1 ? files[0].name : `${files.length} Work Programme PDF`,
            fileType: 'application/pdf',
            uploadedAt: new Date().toISOString(), fileText: '',
            extractedBy: 'horizon-matcher-ingest', extractedChars: 0, extractionError: '',
          },
        };
      });
      if (target !== clusterId) router.push(`/fit/${target}`);
      setFit(null); setTopicFits([]); setOtherTopicFits([]); setSelectedTopic(null); setFitStarted(false);
    } catch (err) { setFitError(`Errore upload: ${formatError(err)}`); }
    finally { setUploading(false); e.target.value = ''; }
  };

  const applyProfile = () => {
    if (!cluster || !selectedProfileId || selectedProfileId === 'manual:current') return;
    const sel = profileChoices.find(p => p.id === selectedProfileId); if (!sel) return;
    const merged = [...new Set([
      ...cluster.clusterInterests.trim().split('\n'),
      ...sel.keywords,
    ].map(x => x.trim()).filter(Boolean))].join('\n');
    setClusterData(prev => {
      const c = prev[clusterId];
      return c ? {
        ...prev, [clusterId]: {
          ...c,
          companyDescription: sel.description || sel.name || c.companyDescription,
          clusterInterests: merged || c.clusterInterests,
        },
      } : prev;
    });
  };

  const runFit = async () => {
    if (!cluster || !canFit) return;
    let outcomeTs: number | null = null, hasOutcome = false;
    setFitStarted(true); setFitBooting(true); setFitFinishing(false);
    setFitClosing(false); setFitClosingExit(false); setFitLoading(true); setFitError('');
    pushFitStream({ active: true, stage: 'boot', title: 'Avvio Fit', lines: ['Inizializzo pipeline...'] });
    const bootTimer = window.setTimeout(() => setFitBooting(false), 950);
    try {
      await apiGet<{ status: string }>('/api/health');
      const live = await apiGet<{ calls_json?: boolean; index_faiss?: boolean; metadata_json?: boolean; qa_report_json?: boolean }>('/api/horizon-matcher/status');
      setMatcherStatus(live);
      if (!(live.calls_json && live.index_faiss && live.metadata_json))
        throw new Error('Carica un PDF Work Programme prima di avviare il fit.');

      pushFitStream({ active: true, stage: 'scoring', title: 'Scoring', lines: ['Backend online.', 'Calcolo fit semantico + keyword + vincoli...'] });

      const tags = tokenize(cluster.clusterInterests);
      const clusterName = CLUSTER_TO_NAME[clusterId] || clusterId;

      const scored = await apiPost<HorizonMatcherResponse>('/api/horizon-matcher/score', {
        profile: {
          description: cluster.companyDescription,
          mission: cluster.companyDescription,
          technical_knowhow: cluster.clusterInterests,
          keywords: tags,
          trl_current: cluster.trlCurrent ?? 5,
          is_sme: cluster.isSme ?? false,
          ssh_capacity: cluster.sshCapacity ?? false,
          fair_compliant: cluster.fairCompliant ?? false,
          gender_dimension_active: cluster.genderDimensionActive ?? false,
          clusters_interest: [clusterName],
        },
        top_n: 10,
      });

      const top = scored.results.map(mapMatcherResultToPreview);
      const other = (scored.other_results || []).map(mapMatcherResultToPreview);
      setTopicFits(top); setOtherTopicFits(other);

      const avg = top.length > 0 ? Math.round(top.reduce((s, r) => s + r.overallFit, 0) / top.length) : 0;
      const rec = avg >= 55 ? 'GO' : avg >= 30 ? 'WATCH' : 'NO-GO';
      const semAvg = scored.results.length > 0
        ? Math.round(scored.results.reduce((s, r) => s + (r.score_breakdown.semantic_score || 0), 0) / scored.results.length * 100)
        : avg;
      const kwAvg = scored.results.length > 0
        ? Math.round(scored.results.reduce((s, r) => s + (r.score_breakdown.bm25_score || 0), 0) / scored.results.length * 100)
        : avg;

      setFit({
        score: avg,
        recommendation: rec as FitSummary['recommendation'],
        explanation: [
          `Fit calcolato su ${scored.total_calls} call Horizon Europe.`,
          `Semantica 50% + BM25 30% + Vincoli tecnici 20%.`,
          `Cluster: ${clusterName} · TRL corrente: ${cluster.trlCurrent ?? 5}`,
        ],
        gaps: top.flatMap(m => m.mustHaveGaps).slice(0, 8),
        semanticScore: semAvg,
        keywordScore: kwAvg,
      });

      hasOutcome = true; outcomeTs = Date.now();
      pushFitStream({
        active: true, stage: 'done', title: 'Completato',
        lines: [`Score: ${avg}/100`, `Raccomandazione: ${rec}`],
        topics: top.slice(0, 4).map((m, i) => ({ id: i + 1, score: Math.round(m.overallFit), recommendation: m.recommendation })),
      });
      if (top.length === 0) setFitError('Nessuna call valutata. Verifica il PDF e riprova.');
    } catch (err) {
      setFit(null); setTopicFits([]); setOtherTopicFits([]); setSelectedTopic(null);
      pushFitStream({ active: true, stage: 'error', title: 'Errore', lines: [formatError(err)] });
      setFitError(formatError(err));
    } finally {
      window.clearTimeout(bootTimer);
      if (hasOutcome && outcomeTs) {
        const rem = outcomeTs + FIT_OVERLAY_MIN_AFTER_OUTCOME_MS - Date.now();
        if (rem > 0) await new Promise(r => window.setTimeout(r, rem));
      }
      if (hasOutcome) {
        setFitFinishing(true);
        await new Promise(r => window.setTimeout(r, 1250));
        setFitFinishing(false); setFitClosing(true);
      } else {
        setFitLoading(false); setFitFinishing(false); setFitClosing(false);
        setFitBooting(false);
        pushFitStream({ active: false, stage: 'idle', title: '', lines: [] });
      }
    }
  };

  const onAcceptOutcome = () => {
    if (!fitClosing) return;
    setFitClosingExit(true);
    window.setTimeout(() => {
      setFitLoading(false); setFitClosing(false); setFitClosingExit(false);
      setFitBooting(false);
      pushFitStream({ active: false, stage: 'idle', title: '', lines: [] });
    }, 440);
  };
  const onOpenTopCall = () => { if (topicFits.length > 0) openTopicDetail(topicFits[0], 0); onAcceptOutcome(); };
  const onRecompute = () => {
    setFitClosingExit(true);
    window.setTimeout(() => {
      setFitLoading(false); setFitClosing(false); setFitClosingExit(false);
      setFitBooting(false); setFitFinishing(false);
      void runFit();
    }, 260);
  };

  if (!validCluster) return (
    <section><h1>Cluster non valido</h1><Link href="/">Torna alla home</Link></section>
  );

  return (
    <section className="pipeline-page">

      {/* ── Hero ─────────────────────────────────────────── */}
      <div className="pipeline-hero">
        <div className="pipeline-hero-top">
          <p className="pipeline-hero-kicker">Fit Workspace</p>
          <h1 className="pipeline-hero-headline">{clusterId} — {CLUSTER_TO_NAME[clusterId] || ''}</h1>
          <p className="pipeline-hero-subtitle">Analisi affidabilità, ranking call e decisioni operative.</p>
          <div className="pipeline-hero-links">
            <Link className="pipeline-hero-link" href="/">Overview</Link>
            <a className="pipeline-hero-link" href="#fit-workbench">Avvia Fit</a>
          </div>
        </div>
        <div className="pipeline-hero-media">
          <div className="pipeline-hero-image" style={{ backgroundImage: 'url(/images/IDG_GBionics_render_021_rK-sZdFO9s-rgTKZOlOl6.jpg)' }} />
          <div className="pipeline-hero-vignette" />
        </div>
      </div>

      {/* ── Work Programme ───────────────────────────────── */}
      <div className="pipeline-section">
        <div className="fit-section-header">
          <p className="fit-eyebrow">Dati di input</p>
          <h3>Work Programme</h3>
        </div>

        <div className="fit-status-row">
          <div className={`fit-status-pill ${matcherReady ? 'fit-status-pill--ok' : 'fit-status-pill--warn'}`}>
            <span className="fit-status-dot" />
            {matcherReady ? 'Indice pronto' : 'Upload richiesto'}
          </div>
          {cluster?.fileName && <span className="fit-file-chip">{cluster.fileName}</span>}
          {cluster?.uploadedAt && (
            <span className="fit-meta">
              {new Date(cluster.uploadedAt).toLocaleString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>

        <div className="fit-upload-area">
          <label className={`fit-upload-btn ${uploading ? 'is-loading' : ''}`}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden>
              <path d="M10 13V3m0 0L6.5 6.5M10 3l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3.5 14v1.75A1.75 1.75 0 0 0 5.25 17.5h9.5a1.75 1.75 0 0 0 1.75-1.75V14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
            {uploading ? 'Caricamento...' : 'Carica PDF Work Programme'}
            <input type="file" accept="application/pdf,.pdf" multiple onChange={onUploadPdf} disabled={uploading} style={{ display: 'none' }} />
          </label>
          {cluster?.fileName && (
            <button className="fit-remove-btn" onClick={removeFile} type="button">Rimuovi</button>
          )}
        </div>

        {uploadMessage && <p className="fit-upload-msg">{uploadMessage}</p>}
      </div>

      {/* ── Profilo Azienda ──────────────────────────────── */}
      <div className="pipeline-section" id="fit-workbench">
        <div className="fit-section-header">
          <p className="fit-eyebrow">Configurazione</p>
          <h3>Profilo Azienda</h3>
        </div>

        {/* Profile selector from CRM */}
        <div className="fit-profile-toolbar">
          <select
            value={selectedProfileId}
            onChange={e => setSelectedProfileId(e.target.value)}
            disabled={profilesLoading}
            className="fit-select"
          >
            {profileChoices.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <button type="button" onClick={applyProfile}
            disabled={!selectedProfileId || selectedProfileId === 'manual:current'}
            className="fit-btn-secondary">
            Autopopola
          </button>
          <button type="button" onClick={() => { void refreshProfiles(); }}
            disabled={profilesLoading} className="fit-btn-ghost">
            {profilesLoading ? '…' : 'Aggiorna'}
          </button>
        </div>

        {/* Description & keywords */}
        <div className="fit-field">
          <label className="fit-label">
            Descrizione azienda <span className="fit-label-sub">semantic fit — 50%</span>
          </label>
          <textarea
            rows={5}
            className="fit-textarea"
            placeholder="Competenze, tecnologie, track record, settore, obiettivi strategici…"
            value={cluster?.companyDescription ?? ''}
            onChange={e => updateClusterField('companyDescription', e.target.value)}
          />
        </div>

        <div className="fit-field">
          <label className="fit-label">
            Area di ricerca / keyword <span className="fit-label-sub">BM25 keyword fit — 30%</span>
          </label>
          <textarea
            rows={4}
            className="fit-textarea"
            placeholder="Keyword separate da virgola o a capo: AI, digital twin, cybersecurity, circular economy…"
            value={cluster?.clusterInterests ?? ''}
            onChange={e => updateClusterField('clusterInterests', e.target.value)}
          />
        </div>

        {/* Constraints — 20% of score */}
        <div className="fit-constraints-section">
          <p className="fit-label">
            Vincoli tecnici <span className="fit-label-sub">constraints score — 20%</span>
          </p>

          {/* TRL slider */}
          <div className="fit-trl-row">
            <label className="fit-trl-label">TRL corrente</label>
            <input
              type="range"
              min={1} max={9}
              value={cluster?.trlCurrent ?? 5}
              onChange={e => updateClusterField('trlCurrent', Number(e.target.value))}
              className="fit-trl-slider"
            />
            <span className="fit-trl-badge">{cluster?.trlCurrent ?? 5}</span>
            <span className="fit-trl-desc">{TRL_LABELS[cluster?.trlCurrent ?? 5]}</span>
          </div>

          {/* Boolean flags */}
          <div className="fit-flags-row">
            <label className="fit-flag-item">
              <input
                type="checkbox"
                checked={cluster?.isSme ?? false}
                onChange={e => updateClusterField('isSme', e.target.checked)}
              />
              <span>PMI / SME</span>
            </label>
            <label className="fit-flag-item">
              <input
                type="checkbox"
                checked={cluster?.sshCapacity ?? false}
                onChange={e => updateClusterField('sshCapacity', e.target.checked)}
              />
              <span>SSH capacity</span>
            </label>
            <label className="fit-flag-item">
              <input
                type="checkbox"
                checked={cluster?.fairCompliant ?? false}
                onChange={e => updateClusterField('fairCompliant', e.target.checked)}
              />
              <span>FAIR data</span>
            </label>
            <label className="fit-flag-item">
              <input
                type="checkbox"
                checked={cluster?.genderDimensionActive ?? false}
                onChange={e => updateClusterField('genderDimensionActive', e.target.checked)}
              />
              <span>Gender dimension</span>
            </label>
          </div>
        </div>
      </div>

      {/* ── Avvia Fit ────────────────────────────────────── */}
      <div className="pipeline-section">
        <div className="fit-run-layout">
          <div>
            <div className="fit-section-header" style={{ marginBottom: '0.2rem' }}>
              <p className="fit-eyebrow">Analisi</p>
              <h3 style={{ margin: 0 }}>Fit Analysis</h3>
            </div>
            <p className="fit-meta">Semantica 50% · BM25 keyword 30% · Vincoli normativi 20%</p>
            {!matcherReady && <p className="fit-hint">Carica prima il PDF Work Programme.</p>}
            {matcherReady && !canFit && <p className="fit-hint">Compila descrizione e area di ricerca per attivare il fit.</p>}
            {fitError && <p className="fit-error">{fitError}</p>}
          </div>
          <button
            className="fit-run-btn"
            onClick={() => { void runFit(); }}
            disabled={!canFit || fitLoading}
          >
            {fitLoading ? 'Calcolo…' : 'Avvia Fit'}
          </button>
        </div>
      </div>

      {/* ── Score Overview ───────────────────────────────── */}
      {fit && (
        <div className="pipeline-section">
          <div className="fit-section-header">
            <p className="fit-eyebrow">Risultato</p>
            <h3>Score Overview</h3>
          </div>
          <div className="fit-scores-grid">
            <ScoreRing value={fit.score} label="Overall" />
            <ScoreRing value={fit.semanticScore} label="Semantica" />
            <ScoreRing value={fit.keywordScore} label="Keyword" />
            <div className="fit-rec-block">
              <span className="fit-rec-label">Raccomandazione</span>
              <RecommendationBadge value={fit.recommendation} />
            </div>
          </div>
          <ul className="fit-explanation">
            {fit.explanation.map((line, i) => <li key={i}>{line}</li>)}
          </ul>
        </div>
      )}

      {/* ── Top 10 Call ──────────────────────────────────── */}
      <div className="pipeline-section">
        <div className="fit-section-header">
          <p className="fit-eyebrow">Ranking</p>
          <h3>Top 10 Call</h3>
        </div>
        {!matcherReady ? (
          <p className="fit-hint">Carica un PDF Work Programme per generare la classifica.</p>
        ) : !canFit ? (
          <p className="fit-hint">Compila il profilo per calcolare il ranking.</p>
        ) : !fitStarted ? (
          <p className="fit-hint">Premi "Avvia Fit" per generare le call.</p>
        ) : topicFits.length === 0 ? (
          <p className="fit-hint">Nessuna call identificata. Verifica il PDF e riprova.</p>
        ) : (
          <div className="pipeline-topic-grid">
            {topicFits.map((t, idx) => (
              <article key={`${t.topicTitle}-${idx}`} className="pipeline-topic-card fit-call-card">
                <div className="fit-call-top">
                  <span className="fit-rank-badge">#{idx + 1}</span>
                  <RecommendationBadge value={t.recommendation} />
                </div>
                <h4 className="fit-call-title" title={t.topicTitle}>{t.topicTitle}</h4>
                {t.summary && <p className="fit-call-summary">{t.summary}</p>}
                <div className="fit-call-body">
                  <SpiderMini axes={t.spiderAxes} />
                  <div className="fit-call-scores">
                    <div className="fit-score-row"><span>Overall</span><strong>{Math.round(t.overallFit)}</strong></div>
                    <div className="fit-score-row"><span>Semantica</span><strong>{Math.round(t.readinessScore)}</strong></div>
                    <div className="fit-score-row"><span>Keyword</span><strong>{Math.round(t.partnerDependencyScore)}</strong></div>
                    <div className="fit-score-row"><span>Ruolo</span><strong className="fit-score-row-mono">{t.recommendedRole.slice(0, 22)}</strong></div>
                  </div>
                </div>
                {t.mustHaveGaps.length > 0 && (
                  <p className="fit-call-gaps">{t.mustHaveGaps.join(' · ')}</p>
                )}
                <button className="fit-call-btn" onClick={() => openTopicDetail(t, idx)}>
                  Dettaglio →
                </button>
              </article>
            ))}
          </div>
        )}
      </div>

      {/* ── Altre Call ───────────────────────────────────── */}
      {fitStarted && otherTopicFits.length > 0 && (
        <div className="pipeline-section">
          <div className="fit-section-header">
            <p className="fit-eyebrow">Esteso</p>
            <h3>Altre Call ({otherTopicFits.length})</h3>
          </div>
          <div className="pipeline-topic-grid">
            {otherTopicFits.map((t, idx) => (
              <article key={`other-${idx}`} className="pipeline-topic-card fit-call-card fit-call-card--secondary">
                <div className="fit-call-top">
                  <span className="fit-rank-badge fit-rank-badge--secondary">#{idx + 11}</span>
                  <RecommendationBadge value={t.recommendation} />
                </div>
                <h4 className="fit-call-title" title={t.topicTitle}>{t.topicTitle}</h4>
                {t.summary && <p className="fit-call-summary">{t.summary}</p>}
                <div className="fit-score-row"><span>Overall</span><strong>{Math.round(t.overallFit)}</strong></div>
                <button className="fit-call-btn" onClick={() => openTopicDetail(t, idx + 10)}>
                  Dettaglio →
                </button>
              </article>
            ))}
          </div>
        </div>
      )}

      {/* ── Dettaglio Call ───────────────────────────────── */}
      <div className="pipeline-section" id="fit-selected-call">
        <div className="fit-section-header">
          <p className="fit-eyebrow">Dettaglio</p>
          <h3>Call Selezionata</h3>
        </div>
        {!selectedTopic ? (
          <p className="fit-hint">Seleziona una call dal ranking per vedere il dettaglio completo.</p>
        ) : (
          <div className="fit-detail">

            {/* Header */}
            <div className="fit-detail-head">
              <div className="fit-detail-meta">
                <span className="fit-rank-badge">#{selectedTopic.rank}</span>
                <RecommendationBadge value={selectedTopic.topic.recommendation} />
                {selectedTopic.topic.summary && (
                  <span className="fit-meta">{selectedTopic.topic.summary}</span>
                )}
              </div>
              <h4 className="fit-detail-title">{selectedTopic.topic.topicTitle}</h4>
              {selectedTopic.topic.callData?.deadline && (
                <p className="fit-meta">Deadline: {selectedTopic.topic.callData.deadline}</p>
              )}
              {selectedTopic.topic.callData?.budget_indicative && (
                <p className="fit-meta">Budget: {selectedTopic.topic.callData.budget_indicative}</p>
              )}
              {selectedTopic.topic.callData?.source_documents && selectedTopic.topic.callData.source_documents.length > 0 && (
                <p className="fit-meta">
                  Fonte: {selectedTopic.topic.callData.source_documents.join(', ')}
                  {selectedTopic.topic.callData.source_pages && selectedTopic.topic.callData.source_pages.length > 0
                    ? ` · p.${selectedTopic.topic.callData.source_pages.join(', ')}`
                    : ''}
                </p>
              )}
            </div>

            {/* Spider + Scores side by side */}
            <div className="fit-detail-body">
              <div className="fit-detail-spider-wrap">
                <SpiderFull axes={selectedTopic.topic.spiderAxes} />
              </div>
              <div className="fit-detail-scores-col">
                <div className="fit-scores-grid fit-scores-grid--compact">
                  <ScoreRing value={Math.round(selectedTopic.topic.overallFit)} label="Overall" />
                  <ScoreRing value={Math.round(selectedTopic.topic.readinessScore)} label="Semantica" />
                  <ScoreRing value={Math.round(selectedTopic.topic.confidence)} label="Confidence" />
                </div>
                {selectedTopic.topic.mustHaveGaps.length > 0 && (
                  <div className="fit-detail-gaps">
                    <p className="fit-label" style={{ marginBottom: '0.4rem' }}>Gap identificati</p>
                    {selectedTopic.topic.mustHaveGaps.map((g, i) => (
                      <span key={i} className="fit-gap-chip">{g}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Justification */}
            <div className="fit-detail-block">
              <p className="fit-detail-block-label">Giustificazione (AI Explainability)</p>
              <p className="fit-detail-text">{selectedTopic.topic.topicText}</p>
            </div>

            {/* Score breakdown */}
            <div className="fit-detail-block">
              <ScoreBreakdown breakdown={selectedTopic.topic.scoreBreakdown} />
            </div>

            {/* Expected Outcomes & Scope from PDF */}
            {selectedTopic.topic.callData?.expected_outcomes && (
              <div className="fit-detail-block">
                <p className="fit-detail-block-label">Expected Outcomes (dal PDF)</p>
                <p className="fit-detail-text fit-detail-text--muted">
                  {selectedTopic.topic.callData.expected_outcomes.slice(0, 1200)}
                  {selectedTopic.topic.callData.expected_outcomes.length > 1200 ? '…' : ''}
                </p>
              </div>
            )}
            {selectedTopic.topic.callData?.scope && (
              <div className="fit-detail-block">
                <p className="fit-detail-block-label">Scope (dal PDF)</p>
                <p className="fit-detail-text fit-detail-text--muted">
                  {selectedTopic.topic.callData.scope.slice(0, 1200)}
                  {selectedTopic.topic.callData.scope.length > 1200 ? '…' : ''}
                </p>
              </div>
            )}

            {/* Consortium suggestions */}
            <div className="fit-detail-block">
              <p className="fit-detail-block-label">Suggerimenti Consorzio (da CRM)</p>
              <ConsortiumSuggestions
                callTitle={selectedTopic.topic.topicTitle}
                callText={selectedTopic.topic.topicText}
              />
            </div>

          </div>
        )}
      </div>

      {/* ── Fit Overlay ──────────────────────────────────── */}
      {fitLoading && (
        <div className={`fit-loading-overlay${fitBooting ? ' is-booting' : ''}${fitFinishing ? ' is-finishing' : ''}${fitClosing ? ' is-outcome' : ''}${fitClosingExit ? ' is-closing' : ''}`} aria-live="polite">
          <FitConstellationLoader phase={loaderPhase} />
          {fitClosing && fit && (
            <div className="fit-outcome-card" role="status">
              <h4>Fit Completato</h4>
              <p><strong>Score:</strong> {fit.score}/100</p>
              <p><strong>Raccomandazione:</strong> {fit.recommendation}</p>
              <p className="small">Top call analizzate: {topicFits.length}</p>
              <div className="fit-outcome-actions">
                <button onClick={onOpenTopCall}>Apri Top Call</button>
                <button onClick={onRecompute}>Ricalcola</button>
                <button onClick={onAcceptOutcome}>Continua</button>
              </div>
            </div>
          )}
          <div className="fit-loading-label">
            {fitClosing ? 'Fit pronto.' : fitFinishing ? 'Consolidamento finale…' : fitBooting ? 'Inizializzo motore…' : 'Analisi in corso…'}
          </div>
        </div>
      )}
    </section>
  );
}
