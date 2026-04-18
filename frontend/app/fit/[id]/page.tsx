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
import { ExportPDFButton } from '@/components/ExportPDFButton';
import type {
  HorizonMatcherCallData,
  HorizonMatcherProfilePayload,
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

const EMPTY_CLUSTER_DATA: ClusterData = {
  fileName: '',
  fileType: '',
  uploadedAt: '',
  fileText: '',
  extractedBy: '',
  extractedChars: 0,
  extractionError: '',
  companyDescription: '',
  clusterInterests: '',
  trlCurrent: 5,
  budgetCompanyAvailable: 0,
  budgetMax: null,
  isSme: false,
  sshCapacity: false,
  fairCompliant: false,
  genderDimensionActive: false,
  genderBalanceRequired: false,
};

// ── Types ────────────────────────────────────────────────────────────────────

type FitSummary = {
  score: number;
  recommendation: 'GO' | 'WATCH' | 'NO-GO';
  explanation: string[];
  gaps: string[];
  excellenceScore: number;
  impactScore: number;
  implementationScore: number;
  techFitScore: number;
  consistencyRatio: number;
  solverStatus: string;
};

type TopicDecisionCardPreview = {
  callId: string;
  topicTitle: string;
  topicText: string;
  summary: string;
  deadline: string | null;
  score: number;
  recommendation: string;
  overallFit: number;
  implementationScore: number;
  impactScore: number;
  techFitScore: number;
  excellenceScore: number;
  submissionPriority: number;
  confidence: number;
  recommendedRole: string;
  whyFit: string[];
  whyNotFit: string[];
  mustHaveGaps: string[];
  niceToHaveGaps: string[];
  suggestedPartnerTypes: string[];
  suggestedActions: string[];
  aiFitReview: NonNullable<HorizonMatcherResult['explanation']>['ai_fit_review'] | null;
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
  const r = Math.round(row.fit_score_100);
  const excellence = Math.round((row.score_breakdown.local_scores?.excellence || 0) * 100);
  const impact = Math.round((row.score_breakdown.local_scores?.impact || 0) * 100);
  const implementation = Math.round((row.score_breakdown.local_scores?.implementation || 0) * 100);
  const techFit = Math.round((row.score_breakdown.local_scores?.tech_fit || 0) * 100);
  const clear = row.explanation?.clear_explanation;
  const aiReview = row.explanation?.ai_fit_review ?? null;
  const gaps: string[] = [];
  if ((row.score_breakdown.constraints_applied?.trl_violation as boolean | undefined) === true) gaps.push('Cap TRL applicato');
  if ((row.score_breakdown.constraints_applied?.sme_required as boolean | undefined) && !(row.score_breakdown.constraints_applied?.sme_ok as boolean | undefined)) gaps.push('Vincolo SME non soddisfatto');
  if ((row.score_breakdown.constraints_applied?.budget_company_available as number | undefined) !== undefined
    && (row.score_breakdown.constraints_applied?.budget_max as number | undefined) !== undefined
    && Number(row.score_breakdown.constraints_applied?.budget_company_available) < Number(row.score_breakdown.constraints_applied?.budget_max)) {
    gaps.push('Cap budget applicato');
  }
  if (!row.score_breakdown.consistency_ok) gaps.push('AHP inconsistente');
  return {
    callId: row.call_id,
    topicTitle: `${row.call_id} — ${row.title}`,
    topicText: row.justification,
    summary: `${row.cluster || ''}${row.type_of_action ? ` · ${row.type_of_action}` : ''}`,
    deadline: row.call_data?.deadline ?? null,
    score: r,
    recommendation: r >= 55 ? 'GO' : r >= 30 ? 'WATCH' : 'NO-GO',
    overallFit: r,
    implementationScore: implementation,
    impactScore: impact,
    techFitScore: techFit,
    excellenceScore: excellence,
    submissionPriority: r,
    confidence: clamp(Math.round((row.score_breakdown.consistency_ok ? 92 : 68) - row.score_breakdown.cr * 100), 35, 96),
    recommendedRole: aiReview?.ideal_role?.replace('_', ' ') || row.type_of_action || 'N/A',
    whyFit: aiReview?.strengths?.length ? aiReview.strengths : (clear?.testo_semplice ? [clear.testo_semplice] : [row.justification]),
    whyNotFit: aiReview?.risks?.length ? aiReview.risks : [],
    mustHaveGaps: [...gaps, ...(clear?.gap_principali || []), ...(aiReview?.risks || [])].slice(0, 8),
    niceToHaveGaps: [],
    suggestedPartnerTypes: aiReview?.consortium_notes || [],
    suggestedActions: aiReview?.next_steps?.length ? aiReview.next_steps : (clear?.azioni_concrete || ['Verifica readiness consorzio', 'Controlla requisiti specifici nel testo']),
    aiFitReview: aiReview,
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

function AIFitBadge({ value }: { value?: string }) {
  const label = value === 'strong_fit'
    ? 'AI strong fit'
    : value === 'conditional_fit'
      ? 'AI conditional fit'
      : value === 'weak_fit'
        ? 'AI weak fit'
        : 'AI review';
  const cls = value === 'strong_fit'
    ? 'fit-badge fit-badge--go'
    : value === 'conditional_fit'
      ? 'fit-badge fit-badge--watch'
      : 'fit-badge fit-badge--nogo';
  return <span className={cls}>{label}</span>;
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
  const rows = [
    { label: 'Excellence', key: 'excellence', desc: 'Qualita scientifica e allineamento con gli expected outcomes.' },
    { label: 'Impact', key: 'impact', desc: 'Potenziale strategico e valore atteso del topic.' },
    { label: 'Implementation', key: 'implementation', desc: 'Fattibilita operativa dopo l\'applicazione dei vincoli LP.' },
    { label: 'Tech Fit', key: 'tech_fit', desc: 'Compatibilita tecnico-metodologica con scope e know-how.' },
  ];
  return (
    <div className="fit-breakdown">
      <h5 className="fit-breakdown-title">Come e' stato ottimizzato</h5>
      {rows.map(row => {
        const contribution = Math.round((breakdown.breakdown?.[row.key] || 0) * 100);
        const local = Math.round((breakdown.local_scores?.[row.key] || 0) * 100);
        const weight = Math.round((breakdown.weights?.[row.key] || 0) * 100);
        return (
          <div key={row.key} className="fit-breakdown-row">
            <div className="fit-breakdown-meta">
              <span className="fit-breakdown-name">{row.label}</span>
              <span className="fit-breakdown-weight">peso {weight}%</span>
              <span className="fit-breakdown-pct">{contribution}%</span>
            </div>
            <div className="fit-breakdown-bar-track">
              <div className="fit-breakdown-bar-fill" style={{ width: `${contribution}%` }} />
            </div>
            <p className="fit-breakdown-desc">{row.desc}</p>
            <p className="fit-breakdown-desc fit-breakdown-desc--mono">
              score locale {local}% · contributo LP ottimo {Math.round((breakdown.optimal_contributions?.[row.key] || 0) * 100)}%
            </p>
          </div>
        );
      })}
      <div className="fit-breakdown-footer">
        <span>
          Fit score {Math.round(breakdown.fit_score_100)}% · Solver {breakdown.solver} ({breakdown.status})
          {` · CR ${breakdown.cr.toFixed(4)} · ${breakdown.consistency_ok ? 'Consistency OK' : 'Consistency warning'}`}
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
  const [exportLoading, setExportLoading] = useState(false);
  const [exportMessage, setExportMessage] = useState('');
  const [exportAllCalls, setExportAllCalls] = useState(false);
  const [fitBooting, setFitBooting] = useState(false);
  const [fitFinishing, setFitFinishing] = useState(false);
  const [fitClosing, setFitClosing] = useState(false);
  const [fitClosingExit, setFitClosingExit] = useState(false);
  const [fitError, setFitError] = useState('');

  const loaderPhase = fitFinishing || fitClosing || fitClosingExit || exportLoading ? 'finishing' : fitBooting ? 'booting' : 'running';
  const cluster = clusterData[clusterId];
  const validCluster = CLUSTERS.includes(clusterId);
  const matcherReady = Boolean(matcherStatus?.calls_json);

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
      store.clusterData[clusterId] = { ...EMPTY_CLUSTER_DATA };
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

  const buildProfilePayload = (): HorizonMatcherProfilePayload | null => {
    if (!cluster) return null;
    const clusterName = CLUSTER_TO_NAME[clusterId] || clusterId;
    return {
      description: cluster.companyDescription,
      mission: cluster.companyDescription,
      technical_knowhow: cluster.clusterInterests,
      keywords: tokenize(cluster.clusterInterests),
      trl_current: cluster.trlCurrent ?? 5,
      budget_company_available: cluster.budgetCompanyAvailable ?? 0,
      budget_max: cluster.budgetMax ?? null,
      is_sme: cluster.isSme ?? false,
      ssh_capacity: cluster.sshCapacity ?? false,
      fair_compliant: cluster.fairCompliant ?? false,
      gender_dimension_active: cluster.genderDimensionActive ?? false,
      gender_balance_required: cluster.genderBalanceRequired ?? false,
      clusters_interest: [clusterName],
    };
  };

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
        return {
          ...prev,
          [target]: {
            ...(prev[target] ?? prev[clusterId] ?? EMPTY_CLUSTER_DATA),
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
      if (!live.calls_json)
        throw new Error('Carica un PDF Work Programme prima di avviare il fit.');

      pushFitStream({ active: true, stage: 'scoring', title: 'Scoring', lines: ['Backend online.', 'Ottimizzo con AHP + Gurobi LP...'] });

      const profilePayload = buildProfilePayload();
      if (!profilePayload) throw new Error('Profilo non disponibile per il calcolo fit.');
      const clusterName = CLUSTER_TO_NAME[clusterId] || clusterId;

      const scored = await apiPost<HorizonMatcherResponse>('/api/horizon-matcher/score', {
        profile: profilePayload,
        top_n: 10,
      });

      const top = scored.results.map(mapMatcherResultToPreview);
      const other = (scored.other_results || []).map(mapMatcherResultToPreview);
      setTopicFits(top); setOtherTopicFits(other);

      const avg = top.length > 0 ? Math.round(top.reduce((s, r) => s + r.overallFit, 0) / top.length) : 0;
      const rec = avg >= 55 ? 'GO' : avg >= 30 ? 'WATCH' : 'NO-GO';
      const excellenceAvg = scored.results.length > 0
        ? Math.round(scored.results.reduce((s, r) => s + (r.score_breakdown.local_scores?.excellence || 0), 0) / scored.results.length * 100)
        : avg;
      const impactAvg = scored.results.length > 0
        ? Math.round(scored.results.reduce((s, r) => s + (r.score_breakdown.local_scores?.impact || 0), 0) / scored.results.length * 100)
        : avg;
      const implementationAvg = scored.results.length > 0
        ? Math.round(scored.results.reduce((s, r) => s + (r.score_breakdown.local_scores?.implementation || 0), 0) / scored.results.length * 100)
        : avg;
      const techFitAvg = scored.results.length > 0
        ? Math.round(scored.results.reduce((s, r) => s + (r.score_breakdown.local_scores?.tech_fit || 0), 0) / scored.results.length * 100)
        : avg;
      const topBreakdown = scored.results[0]?.score_breakdown;

      setFit({
        score: avg,
        recommendation: rec as FitSummary['recommendation'],
        explanation: [
          `Fit calcolato su ${scored.total_calls} call Horizon Europe.`,
          `Motore decisionale AHP + Gurobi LP con quattro criteri ottimizzati.`,
          `Cluster: ${clusterName} · TRL corrente: ${cluster.trlCurrent ?? 5} · Solver: ${topBreakdown?.status || 'n/d'}`,
        ],
        gaps: top.flatMap(m => m.mustHaveGaps).slice(0, 8),
        excellenceScore: excellenceAvg,
        impactScore: impactAvg,
        implementationScore: implementationAvg,
        techFitScore: techFitAvg,
        consistencyRatio: topBreakdown?.cr ?? 0,
        solverStatus: topBreakdown?.status || 'Unknown',
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
            {matcherReady ? 'Dataset pronto' : 'Upload richiesto'}
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
            Descrizione azienda <span className="fit-label-sub">input per Excellence e Impact</span>
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
            Area di ricerca / keyword <span className="fit-label-sub">input per Impact e Tech Fit</span>
          </label>
          <textarea
            rows={4}
            className="fit-textarea"
            placeholder="Keyword separate da virgola o a capo: AI, digital twin, cybersecurity, circular economy…"
            value={cluster?.clusterInterests ?? ''}
            onChange={e => updateClusterField('clusterInterests', e.target.value)}
          />
        </div>

        <div className="fit-constraints-section">
          <p className="fit-label">
            Vincoli e risorse <span className="fit-label-sub">input LP e hard constraints</span>
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

          <div className="fit-budget-grid">
            <label className="fit-budget-field">
              <span>Budget disponibile azienda</span>
              <input
                type="number"
                min={0}
                step="1000"
                className="fit-input"
                value={cluster?.budgetCompanyAvailable ?? 0}
                onChange={e => updateClusterField('budgetCompanyAvailable', Number(e.target.value))}
              />
            </label>
            <label className="fit-budget-field">
              <span>Budget massimo manuale (opzionale)</span>
              <input
                type="number"
                min={0}
                step="1000"
                className="fit-input"
                value={cluster?.budgetMax ?? ''}
                onChange={e => updateClusterField('budgetMax', e.target.value === '' ? null : Number(e.target.value))}
                placeholder="Se vuoto usa il budget della call"
              />
            </label>
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
            <label className="fit-flag-item">
              <input
                type="checkbox"
                checked={cluster?.genderBalanceRequired ?? false}
                onChange={e => updateClusterField('genderBalanceRequired', e.target.checked)}
              />
              <span>Gender balance hard cap</span>
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
            <p className="fit-meta">AHP criteria: Excellence · Impact · Implementation · Tech Fit</p>
            {!matcherReady && <p className="fit-hint">Carica prima il PDF Work Programme.</p>}
            {matcherReady && !canFit && <p className="fit-hint">Compila descrizione e area di ricerca per attivare il fit.</p>}
            {fitError && <p className="fit-error">{fitError}</p>}
            {exportMessage && <p className="fit-upload-msg">{exportMessage}</p>}
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
            <ScoreRing value={fit.excellenceScore} label="Excellence" />
            <ScoreRing value={fit.impactScore} label="Impact" />
            <ScoreRing value={fit.implementationScore} label="Implementation" />
            <ScoreRing value={fit.techFitScore} label="Tech Fit" />
            <div className="fit-rec-block">
              <span className="fit-rec-label">Raccomandazione</span>
              <RecommendationBadge value={fit.recommendation} />
              <span className="fit-rec-meta">Solver {fit.solverStatus} · CR {fit.consistencyRatio.toFixed(4)}</span>
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
        <div className="fit-run-layout" style={{ marginBottom: '0.8rem' }}>
          <label className="fit-flag-item" style={{ margin: 0 }}>
            <input
              type="checkbox"
              checked={exportAllCalls}
              onChange={e => setExportAllCalls(e.target.checked)}
              disabled={!matcherReady || !canFit}
            />
            <span>Includi tutte le call (default: Top 15)</span>
          </label>
          <ExportPDFButton
            clusterId={clusterId}
            profile={buildProfilePayload() || {
              description: '',
              mission: '',
              technical_knowhow: '',
              keywords: [],
              trl_current: 5,
              budget_company_available: 0,
              budget_max: null,
              is_sme: false,
              ssh_capacity: false,
              fair_compliant: false,
              gender_dimension_active: false,
              gender_balance_required: false,
              clusters_interest: [CLUSTER_TO_NAME[clusterId] || clusterId],
            }}
            includeAllCallsDefault={exportAllCalls}
            topNDefault={15}
            disabled={!matcherReady || !canFit || !buildProfilePayload()}
            onLoadingChange={setExportLoading}
            onMessage={(msg) => setExportMessage(msg)}
          />
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
                    <div className="fit-score-row"><span>Excellence</span><strong>{Math.round(t.excellenceScore)}</strong></div>
                    <div className="fit-score-row"><span>Impact</span><strong>{Math.round(t.impactScore)}</strong></div>
                    <div className="fit-score-row"><span>Tech Fit</span><strong>{Math.round(t.techFitScore)}</strong></div>
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
                <div className="fit-score-row"><span>Solver</span><strong>{t.scoreBreakdown.status}</strong></div>
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
              <div style={{ marginTop: '0.6rem' }}>
                <ExportPDFButton
                  clusterId={clusterId}
                  profile={buildProfilePayload() || {
                    description: '',
                    mission: '',
                    technical_knowhow: '',
                    keywords: [],
                    trl_current: 5,
                    budget_company_available: 0,
                    budget_max: null,
                    is_sme: false,
                    ssh_capacity: false,
                    fair_compliant: false,
                    gender_dimension_active: false,
                    gender_balance_required: false,
                    clusters_interest: [CLUSTER_TO_NAME[clusterId] || clusterId],
                  }}
                  callIds={[selectedTopic.topic.callId]}
                  includeAllCallsDefault={false}
                  topNDefault={1}
                  disabled={!buildProfilePayload()}
                  onLoadingChange={setExportLoading}
                  onMessage={(msg) => setExportMessage(msg)}
                />
              </div>
            </div>

            {/* Spider + Scores side by side */}
            <div className="fit-detail-body">
              <div className="fit-detail-spider-wrap">
                <SpiderFull axes={selectedTopic.topic.spiderAxes} />
              </div>
              <div className="fit-detail-scores-col">
                <div className="fit-scores-grid fit-scores-grid--compact">
                  <ScoreRing value={Math.round(selectedTopic.topic.overallFit)} label="Overall" />
                  <ScoreRing value={Math.round(selectedTopic.topic.excellenceScore)} label="Excellence" />
                  <ScoreRing value={Math.round(selectedTopic.topic.impactScore)} label="Impact" />
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

            {selectedTopic.topic.aiFitReview && (
              <div className="fit-detail-block">
                <div className="fit-detail-meta" style={{ marginBottom: '0.85rem' }}>
                  <p className="fit-detail-block-label" style={{ margin: 0 }}>AI Copilot del Fit</p>
                  <AIFitBadge value={selectedTopic.topic.aiFitReview.qualitative_fit_label} />
                </div>
                {selectedTopic.topic.aiFitReview.strategic_verdict && (
                  <p className="fit-detail-text" style={{ fontWeight: 700 }}>
                    {selectedTopic.topic.aiFitReview.strategic_verdict}
                  </p>
                )}
                {selectedTopic.topic.aiFitReview.summary && (
                  <p className="fit-detail-text fit-detail-text--muted">
                    {selectedTopic.topic.aiFitReview.summary}
                  </p>
                )}
                <div className="fit-detail-body">
                  <div className="fit-detail-block" style={{ margin: 0 }}>
                    <p className="fit-detail-block-label">Punti di forza letti dal modello</p>
                    <ul className="fit-explanation">
                      {(selectedTopic.topic.aiFitReview.strengths || []).map((item, idx) => <li key={idx}>{item}</li>)}
                    </ul>
                  </div>
                  <div className="fit-detail-block" style={{ margin: 0 }}>
                    <p className="fit-detail-block-label">Rischi e frizioni da gestire</p>
                    <ul className="fit-explanation">
                      {(selectedTopic.topic.aiFitReview.risks || []).map((item, idx) => <li key={idx}>{item}</li>)}
                    </ul>
                  </div>
                </div>
                <div className="fit-detail-body">
                  <div className="fit-detail-block" style={{ margin: 0 }}>
                    <p className="fit-detail-block-label">Prossimi passi consigliati</p>
                    <ul className="fit-explanation">
                      {(selectedTopic.topic.aiFitReview.next_steps || []).map((item, idx) => <li key={idx}>{item}</li>)}
                    </ul>
                  </div>
                  <div className="fit-detail-block" style={{ margin: 0 }}>
                    <p className="fit-detail-block-label">Ruolo e consorzio</p>
                    <p className="fit-detail-text fit-detail-text--muted">
                      Ruolo ideale: {selectedTopic.topic.aiFitReview.ideal_role?.replace('_', ' ') || 'n/d'}
                    </p>
                    <ul className="fit-explanation">
                      {(selectedTopic.topic.aiFitReview.consortium_notes || []).map((item, idx) => <li key={idx}>{item}</li>)}
                    </ul>
                    <p className="fit-detail-text fit-detail-text--muted">
                      Sorgente AI: {selectedTopic.topic.aiFitReview.enabled ? 'modello locale attivo' : 'fallback statico'}{selectedTopic.topic.aiFitReview.model ? ` · ${selectedTopic.topic.aiFitReview.model}` : ''}
                    </p>
                  </div>
                </div>
                {selectedTopic.topic.aiFitReview.reasoning_available && (
                  <div className="fit-detail-block" style={{ margin: 0 }}>
                    <p className="fit-detail-block-label">Ragionamento del modello locale</p>
                    <p className="fit-detail-text fit-detail-text--muted">
                      Trace `thinking` restituito da Ollama per questa review strategica.
                    </p>
                    <pre className="fit-reasoning-trace">
                      {selectedTopic.topic.aiFitReview.reasoning_trace}
                    </pre>
                  </div>
                )}
              </div>
            )}

            {/* Score breakdown */}
            <div className="fit-detail-block">
              <ScoreBreakdown breakdown={selectedTopic.topic.scoreBreakdown} />
            </div>

            <div className="fit-detail-block">
              <p className="fit-detail-block-label">Solver e consistenza</p>
              <p className="fit-detail-text fit-detail-text--muted">
                Solver: {selectedTopic.topic.scoreBreakdown.solver} · Status: {selectedTopic.topic.scoreBreakdown.status} ·
                CR: {selectedTopic.topic.scoreBreakdown.cr.toFixed(4)} ·
                {selectedTopic.topic.scoreBreakdown.consistency_ok ? ' matrice AHP consistente.' : ' matrice AHP da rivedere.'}
              </p>
              <p className="fit-detail-text fit-detail-text--muted">
                Vincoli applicati: {JSON.stringify(selectedTopic.topic.scoreBreakdown.constraints_applied)}
              </p>
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
      {(fitLoading || exportLoading) && (
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
            {exportLoading
              ? 'Generazione report PDF professionale…'
              : fitClosing
                ? 'Fit pronto.'
                : fitFinishing
                  ? 'Consolidamento finale…'
                  : fitBooting
                    ? 'Inizializzo motore…'
                    : 'Analisi in corso…'}
          </div>
        </div>
      )}
    </section>
  );
}
