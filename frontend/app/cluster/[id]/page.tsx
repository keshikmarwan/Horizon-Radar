'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ChangeEvent, useEffect, useMemo, useState } from 'react';
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
import { companyKey, readCrmStore } from '@/lib/crm-store';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';
import type { HorizonMatcherResponse, HorizonMatcherResult, HorizonMatcherUploadResponse } from '@/lib/types';

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
};

type ProfileOption = {
  id: string;
  name: string;
  description: string;
  keywords: string[];
};

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

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function mapMatcherResultToPreview(row: HorizonMatcherResult): TopicDecisionCardPreview {
  const reliability100 = Math.round(row.reliability_score * 100);
  const semantic100 = Math.round((row.score_breakdown.semantic_score || 0) * 100);
  const bm25100 = Math.round((row.score_breakdown.bm25_score || 0) * 100);
  const constraints100 = Math.round((row.score_breakdown.constraints_score || 0) * 100);
  const trl100 = Math.round((row.score_breakdown.trl_score || 0) * 100);
  const mustHaveGaps: string[] = [];
  if (trl100 < 60) mustHaveGaps.push('TRL gap da verificare');
  if (constraints100 < 50) mustHaveGaps.push('Vincoli/eligibility deboli');
  if (!row.score_breakdown.bm25_boost_applied) mustHaveGaps.push('Nessun boost keyword tecnico UE');

  return {
    topicTitle: `${row.call_id} - ${row.title}`,
    topicText: row.justification,
    summary: `${row.cluster || 'Unknown'}${row.type_of_action ? ` • ${row.type_of_action}` : ''}`,
    deadline: null,
    score: reliability100,
    recommendation: reliability100 >= 55 ? 'GO' : reliability100 >= 30 ? 'WATCH' : 'NO-GO',
    overallFit: reliability100,
    gapScore: 100 - constraints100,
    readinessScore: semantic100,
    partnerDependencyScore: bm25100,
    submissionPriority: reliability100,
    confidence: clamp(Math.round(100 - Math.abs(semantic100 - bm25100) * 0.6), 35, 96),
    recommendedRole: row.type_of_action || 'N/A',
    whyFit: [row.justification],
    whyNotFit: [],
    mustHaveGaps,
    niceToHaveGaps: [],
    suggestedPartnerTypes: [],
    suggestedActions: [
      'Verifica readiness consorzio e stakeholder',
      'Controlla requisiti specifici del topic nel testo originale',
    ],
    spiderAxes: row.spider_axes || {},
  };
}

function SpiderMini({ axes }: { axes: Record<string, number> }) {
  const axisDefs = [
    { key: 'trl_alignment', label: 'TRL' },
    { key: 'impact_policy', label: 'Impatto' },
    { key: 'scope_methodology', label: 'Metodo' },
    { key: 'consortium_stakeholders', label: 'Consorzio' },
    { key: 'fair_compliance', label: 'FAIR' },
    { key: 'inclusion_ethics', label: 'Etica' },
  ];
  const cx = 74;
  const cy = 74;
  const outer = 54;
  const values = axisDefs.map((axis) => {
    const raw = axes[axis.key] ?? 1;
    const normalized = clamp((raw - 1) / 4, 0, 1);
    return normalized;
  });
  const points = values
    .map((v, i) => {
      const angle = (-Math.PI / 2) + (i * 2 * Math.PI) / axisDefs.length;
      const r = outer * v;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg viewBox="0 0 148 148" className="pipeline-spider" role="img" aria-label="Spider chart fit">
      {[0.2, 0.4, 0.6, 0.8, 1].map((ratio, idx) => {
        const polyPoints = axisDefs
          .map((_, i) => {
            const angle = (-Math.PI / 2) + (i * 2 * Math.PI) / axisDefs.length;
            const r = outer * ratio;
            const x = cx + Math.cos(angle) * r;
            const y = cy + Math.sin(angle) * r;
            return `${x},${y}`;
          })
          .join(' ');
        return <polygon key={idx} points={polyPoints} className="pipeline-spider-grid" />;
      })}
      {axisDefs.map((axis, i) => {
        const angle = (-Math.PI / 2) + (i * 2 * Math.PI) / axisDefs.length;
        const x2 = cx + Math.cos(angle) * outer;
        const y2 = cy + Math.sin(angle) * outer;
        const tx = cx + Math.cos(angle) * (outer + 12);
        const ty = cy + Math.sin(angle) * (outer + 12);
        return (
          <g key={axis.key}>
            <line x1={cx} y1={cy} x2={x2} y2={y2} className="pipeline-spider-axis" />
            <text x={tx} y={ty} className="pipeline-spider-label" textAnchor="middle" dominantBaseline="middle">
              {axis.label}
            </text>
          </g>
        );
      })}
      <polygon points={points} className="pipeline-spider-fill" />
      <polygon points={points} className="pipeline-spider-stroke" />
    </svg>
  );
}

export default function ClusterPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const clusterId = (params.id || '').toUpperCase() as ClusterId;

  const [clusterData, setClusterData] = useState<Partial<Record<ClusterId, ClusterData>>>({});
  const [instances, setInstances] = useState<ClusterInstanceMeta[]>([]);
  const [activeInstanceId, setActiveInstanceId] = useState('');
  const [isHydrated, setIsHydrated] = useState(false);
  const [fit, setFit] = useState<FitSummary | null>(null);
  const [topicFits, setTopicFits] = useState<TopicDecisionCardPreview[]>([]);
  const [otherTopicFits, setOtherTopicFits] = useState<TopicDecisionCardPreview[]>([]);
  const [matcherStatus, setMatcherStatus] = useState<{
    data_dir?: string;
    calls_json?: boolean;
    index_faiss?: boolean;
    metadata_json?: boolean;
    audit_log?: boolean;
  } | null>(null);
  const [matcherUploadMessage, setMatcherUploadMessage] = useState('');
  const [matcherUploading, setMatcherUploading] = useState(false);
  const [profileOptions, setProfileOptions] = useState<ProfileOption[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(false);
  const [selectedProfileId, setSelectedProfileId] = useState<string>('');
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
  const activeInstance = instances.find((x) => x.id === activeInstanceId) || null;
  const matcherReady = Boolean(matcherStatus?.calls_json && matcherStatus?.index_faiss && matcherStatus?.metadata_json);

  const selectableProfileOptions = useMemo<ProfileOption[]>(() => {
    const manualKeywords = (cluster?.clusterInterests || '')
      .split(/[\n,;|]+/)
      .map((x) => x.trim())
      .filter((x) => x.length >= 2)
      .slice(0, 24);
    return [
      {
        id: 'manual:current',
        name: 'Profilo corrente (manuale)',
        description: cluster?.companyDescription || '',
        keywords: manualKeywords,
      },
      ...profileOptions,
    ];
  }, [cluster?.companyDescription, cluster?.clusterInterests, profileOptions]);

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
      setOtherTopicFits([]);
      setSelectedTopic(null);
      setFitError('');
    }
  }, [cluster]);

  useEffect(() => {
    const loadMatcherStatus = async () => {
      try {
        const status = await apiGet<{
          data_dir?: string;
          calls_json?: boolean;
          index_faiss?: boolean;
          metadata_json?: boolean;
          audit_log?: boolean;
        }>('/api/horizon-matcher/status');
        setMatcherStatus(status);
      } catch (err) {
        setFitError(`Matcher status non disponibile: ${formatError(err)}`);
      }
    };
    void loadMatcherStatus();
  }, []);

  const refreshProfileOptions = async () => {
    setProfilesLoading(true);
    const collected: ProfileOption[] = [];

    try {
      const crm = readCrmStore();
      const tagById = new Map(crm.tags.map((tag) => [tag.id, tag]));
      const byCompany = new Map<string, typeof crm.contacts>();

      for (const contact of crm.contacts) {
        const key = companyKey(contact.company);
        if (!key) continue;
        byCompany.set(key, [...(byCompany.get(key) || []), contact]);
      }

      for (const [key, contacts] of byCompany.entries()) {
        const companyName = contacts[0]?.company?.trim() || key;
        const companyTagLabels = (crm.companyTagIds[key] || [])
          .map((id) => tagById.get(id)?.label || '')
          .filter(Boolean);
        const personalTagLabels = contacts
          .flatMap((c) => c.subTagIds || [])
          .map((id) => tagById.get(id)?.label || '')
          .filter(Boolean);
        const roles = contacts.map((c) => c.role?.trim() || '').filter(Boolean);
        const notes = contacts.map((c) => c.notes?.trim() || '').filter(Boolean);

        const descriptionParts = [
          `Azienda: ${companyName}`,
          roles.length > 0 ? `Ruoli chiave: ${[...new Set(roles)].slice(0, 8).join(', ')}` : '',
          notes.length > 0 ? `Note operative: ${notes.slice(0, 4).join(' | ')}` : '',
        ].filter(Boolean);

        const keywords = [...new Set([...companyTagLabels, ...personalTagLabels, ...roles])]
          .map((x) => x.trim())
          .filter((x) => x.length > 1)
          .slice(0, 24);

        collected.push({
          id: `crm:${key}`,
          name: companyName,
          description: descriptionParts.join('. '),
          keywords,
        });
      }
    } catch {
      // Ignore CRM read errors and continue with API fallback.
    }

    const unique = collected.filter((item, index, arr) =>
      arr.findIndex((other) => other.name.trim().toLowerCase() === item.name.trim().toLowerCase()) === index
    );
    setProfileOptions(unique);
    setProfilesLoading(false);
  };

  useEffect(() => {
    void refreshProfileOptions();
  }, []);

  useEffect(() => {
    if (!selectedProfileId || !selectableProfileOptions.some((p) => p.id === selectedProfileId)) {
      setSelectedProfileId(selectableProfileOptions[0]?.id || '');
    }
  }, [selectedProfileId, selectableProfileOptions]);

  useEffect(() => () => {
    pushFitStream({ active: false, stage: 'idle', title: '', lines: [] });
  }, []);

  const canFit = useMemo(() => {
    if (!cluster) return false;
    return (
      cluster.companyDescription.trim().length > 20 &&
      cluster.clusterInterests.trim().length > 5 &&
      matcherReady
    );
  }, [cluster, matcherReady]);

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
    setOtherTopicFits([]);
    setSelectedTopic(null);
    setFitStarted(false);
    setInstances(listClusterInstances());
  };

  const onChangeInstance = (instanceId: string) => {
    setActiveInstanceId(instanceId);
    const store = switchClusterInstance(instanceId);
    setClusterData(store.clusterData);
    setFit(null);
    setTopicFits([]);
    setOtherTopicFits([]);
    setSelectedTopic(null);
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
    setOtherTopicFits([]);
    setSelectedTopic(null);
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
    setOtherTopicFits([]);
    setSelectedTopic(null);
    setFitStarted(false);
    setFitError('');
    setFitLoading(false);
    setFitBooting(false);
    setFitFinishing(false);
    setFitClosing(false);
    setFitClosingExit(false);
  };

  const openTopicDetail = (topic: TopicDecisionCardPreview, index: number) => {
    setSelectedTopic({ topic, rank: index + 1 });
    if (typeof window !== 'undefined') {
      window.setTimeout(() => {
        document.getElementById('fit-selected-call')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 80);
    }
  };

  const tokenizeInterests = (text: string): string[] =>
    text
      .toLowerCase()
      .split(/[\n,;|]+/)
      .map((x) => x.trim())
      .filter((x) => x.length >= 3)
      .slice(0, 24);

  const onUploadWorkProgrammePdf = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setMatcherUploading(true);
    setMatcherUploadMessage('');
    setFitError('');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const upload = await apiPostFormData<HorizonMatcherUploadResponse>('/api/horizon-matcher/upload-pdf', formData);
      const suggestedClusterId = (upload.suggested_cluster_id || '').toUpperCase() as ClusterId;
      const hasSuggestedCluster = CLUSTERS.includes(suggestedClusterId);
      const targetClusterId = hasSuggestedCluster ? suggestedClusterId : clusterId;
      setMatcherStatus(upload.status as {
        data_dir?: string;
        calls_json?: boolean;
        index_faiss?: boolean;
        metadata_json?: boolean;
        audit_log?: boolean;
      });
      const distribution = upload.cluster_distribution || {};
      const topDistribution = Object.entries(distribution)
        .slice(0, 3)
        .map(([name, count]) => `${name}: ${count}`)
        .join(' | ');
      const clusterHint = upload.detected_cluster
        ? ` Cluster rilevato: ${upload.detected_cluster}${hasSuggestedCluster ? ` -> ${targetClusterId}` : ''}.`
        : '';
      setMatcherUploadMessage(
        `PDF caricato: ${upload.filename}. Call estratte: ${upload.calls_parsed}. Vettori indicizzati: ${upload.indexed_vectors}.${clusterHint}${topDistribution ? ` Distribuzione: ${topDistribution}.` : ''}`
      );
      setClusterData((prev) => {
        const current = prev[clusterId];
        if (!current) return prev;
        const targetCurrent = prev[targetClusterId] || current;
        return {
          ...prev,
          [targetClusterId]: {
            ...targetCurrent,
            fileName: file.name,
            fileType: file.type || 'application/pdf',
            uploadedAt: new Date().toISOString(),
            fileText: '',
            extractedBy: 'horizon-matcher-ingest',
            extractedChars: 0,
            extractionError: '',
          },
        };
      });
      if (targetClusterId !== clusterId) {
        router.push(`/cluster/${targetClusterId}`);
      }
      setFit(null);
      setTopicFits([]);
      setOtherTopicFits([]);
      setSelectedTopic(null);
      setFitStarted(false);
    } catch (err) {
      setFitError(`Errore upload PDF matcher: ${formatError(err)}`);
    } finally {
      setMatcherUploading(false);
      event.target.value = '';
    }
  };

  const applyProfileToForm = () => {
    if (!cluster || !selectedProfileId) return;
    if (selectedProfileId === 'manual:current') return;
    const selected = selectableProfileOptions.find((p) => p.id === selectedProfileId);
    if (!selected) return;

    const mergedInterests = [cluster.clusterInterests.trim(), ...selected.keywords]
      .filter(Boolean)
      .join('\n')
      .split('\n')
      .map((x) => x.trim())
      .filter(Boolean)
      .filter((v, i, arr) => arr.indexOf(v) === i)
      .join('\n');

    setClusterData((prev) => {
      const current = prev[clusterId];
      if (!current) return prev;
      return {
        ...prev,
        [clusterId]: {
          ...current,
          companyDescription: selected.description || selected.name || current.companyDescription,
          clusterInterests: mergedInterests || current.clusterInterests,
        },
      };
    });
  };

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
      const liveMatcherStatus = await apiGet<{
        data_dir?: string;
        calls_json?: boolean;
        index_faiss?: boolean;
        metadata_json?: boolean;
        audit_log?: boolean;
      }>('/api/horizon-matcher/status');
      setMatcherStatus(liveMatcherStatus);
      if (!(liveMatcherStatus.calls_json && liveMatcherStatus.index_faiss && liveMatcherStatus.metadata_json)) {
        throw new Error('Matcher non pronto. Carica un PDF Work Programme prima di avviare il fit.');
      }

      pushFitStream({
        active: true,
        stage: 'profile',
        title: 'Profilo',
        lines: ['Backend online.', 'Creo profilo semantico per il matcher...'],
      });
      const tags = tokenizeInterests(cluster.clusterInterests);
      pushFitStream({
        active: true,
        stage: 'scoring',
        title: 'Scoring',
        lines: [
          `Keyword analizzate: ${tags.length}`,
          'Calcolo fit semantico + keyword + vincoli...',
        ],
      });

      const scored = await apiPost<HorizonMatcherResponse>('/api/horizon-matcher/score', {
        profile: {
          description: cluster.companyDescription,
          mission: cluster.companyDescription,
          technical_knowhow: cluster.clusterInterests,
          keywords: tags,
          trl_current: 5,
          is_sme: false,
          ssh_capacity: false,
          fair_compliant: false,
          gender_dimension_active: false,
          clusters_interest: [clusterId],
        },
        top_n: 10,
      });

      const mappedTop = scored.results.map(mapMatcherResultToPreview);
      const mappedOther = (scored.other_results || []).map(mapMatcherResultToPreview);
      setTopicFits(mappedTop);
      setOtherTopicFits(mappedOther);

      pushFitStream({
        active: true,
        stage: 'ranking',
        title: 'Scoring Server',
        lines: [
          `Call totali: ${scored.total_calls}`,
          `Top call elaborate: ${mappedTop.length}`,
          `Altre call: ${mappedOther.length}`,
        ],
        topics: mappedTop.slice(0, 4).map((m, idx) => ({
          id: idx + 1,
          score: Math.round(m.overallFit),
          recommendation: m.recommendation,
        })),
      });

      const avg = mappedTop.length > 0 ? Math.round(mappedTop.reduce((sum, r) => sum + r.overallFit, 0) / mappedTop.length) : 0;
      const recommendation = avg >= 55 ? 'GO' : avg >= 30 ? 'WATCH' : 'NO-GO';
      const semanticAvg =
        scored.results.length > 0
          ? Math.round(
              (scored.results.reduce((sum, row) => sum + (row.score_breakdown.semantic_score || 0), 0) / scored.results.length) * 100
            )
          : avg;
      const keywordAvg =
        scored.results.length > 0
          ? Math.round(
              (scored.results.reduce((sum, row) => sum + (row.score_breakdown.bm25_score || 0), 0) / scored.results.length) * 100
            )
          : avg;
      setFit({
        score: avg,
        recommendation,
        explanation: [
          `Fit calcolato su ${scored.total_calls} call del Work Programme.`,
          'Metodo ibrido: semantica (50%) + BM25 keyword (30%) + vincoli tecnici/normativi (20%).',
        ],
        gaps: mappedTop.flatMap((m) => m.mustHaveGaps).slice(0, 8),
        semanticScore: semanticAvg,
        keywordScore: keywordAvg,
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
          `Top call elaborate: ${mappedTop.length}`,
        ],
        topics: mappedTop.slice(0, 4).map((m, idx) => ({
          id: idx + 1,
          score: Math.round(m.overallFit),
          recommendation: m.recommendation,
        })),
      });

      if (mappedTop.length === 0) {
        setFitError('Nessuna call valutata. Carica un PDF Work Programme valido e riprova.');
      }
    } catch (err) {
      setFit(null);
      setTopicFits([]);
      setOtherTopicFits([]);
      setSelectedTopic(null);
      pushFitStream({
        active: true,
        stage: 'error',
        title: 'Errore Fit',
        lines: [formatError(err)],
      });
      setFitError(`Errore backend durante Avvia Fit: ${formatError(err)}.`);
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
      openTopicDetail(topicFits[0], 0);
    }
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
      <section className="apple-detail-page pipeline-page">
        <header className="apple-detail-hero">
          <p className="apple-detail-kicker">Pipeline</p>
          <h1>{clusterId}</h1>
        </header>
        <div className="card apple-detail-panel">
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
    <section className="pipeline-page">
      <div className="pipeline-hero">
        <div className="pipeline-hero-top">
          <p className="pipeline-hero-kicker">Pipeline</p>
          <h1 className="pipeline-hero-headline">{clusterId} Fit Workspace</h1>
          <p className="pipeline-hero-subtitle">Valutazione, decisioni e execution in un’unica vista operativa.</p>
          <div className="pipeline-hero-links">
            <Link className="pipeline-hero-link" href="/">Back to uploads</Link>
            <a className="pipeline-hero-link" href="#fit-workbench">Vai al fit</a>
          </div>
        </div>
        <div className="pipeline-hero-media">
          <div
            className="pipeline-hero-image"
            style={{
              backgroundImage: 'url(/images/IDG_GBionics_render_021_rK-sZdFO9s-rgTKZOlOl6.jpg)',
            }}
          />
          <div className="pipeline-hero-vignette" />
        </div>
      </div>

      <div className="pipeline-section">
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

      <div className="pipeline-section">
        <h3>Work Programme Matcher (PDF locale)</h3>
        <p><strong>File attuale:</strong> {cluster.fileName || 'nessun file caricato'}</p>
        <p className="small"><strong>Type:</strong> {cluster.fileType || 'unknown'}</p>
        <p className="small"><strong>Upload:</strong> {cluster.uploadedAt ? new Date(cluster.uploadedAt).toLocaleString() : 'n/d'}</p>
        <p className="small">
          <strong>Matcher status:</strong>{' '}
          {matcherReady ? 'Pronto (calls + indice + metadata)' : 'Non pronto (carica PDF Work Programme)'}
        </p>
        {matcherStatus ? (
          <p className="small">
            calls.json: {matcherStatus.calls_json ? 'ok' : 'missing'} | index.faiss: {matcherStatus.index_faiss ? 'ok' : 'missing'} | metadata.json: {matcherStatus.metadata_json ? 'ok' : 'missing'}
          </p>
        ) : null}
        <div className="row" style={{ marginTop: '0.8rem' }}>
          <label className="link-btn" style={{ cursor: matcherUploading ? 'wait' : 'pointer', opacity: matcherUploading ? 0.7 : 1 }}>
            {matcherUploading ? 'Caricamento PDF...' : 'Carica PDF Work Programme'}
            <input type="file" accept="application/pdf,.pdf" onChange={onUploadWorkProgrammePdf} disabled={matcherUploading} style={{ display: 'none' }} />
          </label>
        </div>
        {matcherUploadMessage ? <p className="small" style={{ marginTop: '0.7rem' }}>{matcherUploadMessage}</p> : null}
        {cluster.fileName ? (
          <div className="row" style={{ marginTop: '0.8rem' }}>
            <button className="btn-danger" onClick={removeClusterFile} type="button">
              Rimuovi file
            </button>
          </div>
        ) : null}
      </div>

      <div className="pipeline-section" id="fit-workbench">
        <h3>Profilo Azienda (per {clusterId})</h3>
        <div className="row" style={{ marginBottom: '0.9rem' }}>
          <select
            value={selectedProfileId}
            onChange={(e) => setSelectedProfileId(e.target.value)}
            disabled={profilesLoading}
            style={{ minWidth: 320 }}
          >
            {selectableProfileOptions.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
          <button type="button" onClick={applyProfileToForm} disabled={!selectedProfileId || selectedProfileId === 'manual:current'}>
            Autopopola da Profiles
          </button>
          <button type="button" onClick={() => { void refreshProfileOptions(); }} disabled={profilesLoading}>
            {profilesLoading ? 'Aggiorno...' : 'Aggiorna lista'}
          </button>
        </div>
        {profileOptions.length === 0 ? <p className="small">Nessun profilo trovato in CRM/DB. Puoi comunque compilare il form manualmente.</p> : null}
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

      <div className="pipeline-section">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h3>Fit Analysis</h3>
          <button onClick={() => { void runBackendFit(); }} disabled={!canFit || fitLoading}>
            {fitLoading ? 'Calcolo in corso...' : 'Avvia Fit'}
          </button>
        </div>
        <p className="small">
          Metodo fit locale: semantica (50%) + BM25 keyword (30%) + vincoli tecnici/normativi (20%).
        </p>
        {!matcherReady ? <p className="small">Carica prima il PDF Work Programme per costruire l'indice matcher.</p> : null}
        {!fitStarted && matcherReady ? <p className="small">Premi "Avvia Fit" per calcolare classifica completa call.</p> : null}
        {fitError ? <p className="small">{fitError}</p> : null}
      </div>

      <div className="pipeline-section">
        <h3>Fit Analysis (Overall Cluster)</h3>
        {!matcherReady ? (
          <p className="small">Matcher non pronto: carica un PDF del Work Programme.</p>
        ) : !canFit ? (
          <p className="small">Compila descrizione azienda e interessi cluster per attivare il fit.</p>
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

      <div className="pipeline-section">
        <h3>Top 10 Call (Schede)</h3>
        {!matcherReady ? (
          <p className="small">Carica un PDF Work Programme per generare la classifica call.</p>
        ) : !canFit ? (
          <p className="small">Compila descrizione/interessi per calcolare il ranking call.</p>
        ) : !fitStarted ? (
          <p className="small">Premi "Avvia Fit" per generare le call.</p>
        ) : topicFits.length === 0 ? (
          <p className="small">Nessuna call identificata nel file. Verifica il PDF e riprova.</p>
        ) : (
          <div className="row pipeline-topic-grid" style={{ alignItems: 'stretch' }}>
            {topicFits.map((t, idx) => (
              <article key={`${t.topicTitle}-${idx}`} className="pipeline-topic-card" style={{ flex: 1, minWidth: 320 }}>
                <h4>#{idx + 1} - {t.topicTitle.slice(0, 90)}</h4>
                <div className="row" style={{ alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.8rem' }}>
                  <SpiderMini axes={t.spiderAxes} />
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <p><strong>Overall fit:</strong> {Math.round(t.overallFit)}/100</p>
                    <p><strong>Recommendation:</strong> <span className="score">{t.recommendation}</span></p>
                    <p><strong>Confidence:</strong> {Math.round(t.confidence)}/100</p>
                  </div>
                </div>
                <p><strong>Gap:</strong> {Math.round(t.gapScore)}/100 | <strong>Readiness:</strong> {Math.round(t.readinessScore)}/100</p>
                <p><strong>Submission priority:</strong> {Math.round(t.submissionPriority)}/100 | <strong>Role:</strong> {t.recommendedRole}</p>
                <p><strong>Riassunto:</strong> <span className="small">{t.summary || 'N/A'}</span></p>
                <p><strong>Must-have gaps:</strong> <span className="small">{t.mustHaveGaps.length > 0 ? t.mustHaveGaps.join(', ') : 'nessun gap critico'}</span></p>
                <p><strong>Justification:</strong> <span className="small">{t.whyFit[0] || 'n/d'}</span></p>
                <p><strong>Partner suggeriti:</strong> <span className="small">{t.suggestedPartnerTypes.length > 0 ? t.suggestedPartnerTypes.join(', ') : 'n/d'}</span></p>
                <button onClick={() => openTopicDetail(t, idx)}>Apri dettaglio call</button>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="pipeline-section">
        <h3>Altre Call</h3>
        {!fitStarted ? (
          <p className="small">Le altre call compaiono dopo il primo fit.</p>
        ) : otherTopicFits.length === 0 ? (
          <p className="small">Nessuna call oltre la Top 10.</p>
        ) : (
          <div className="row pipeline-topic-grid" style={{ alignItems: 'stretch' }}>
            {otherTopicFits.map((t, idx) => (
              <article key={`${t.topicTitle}-other-${idx}`} className="pipeline-topic-card" style={{ flex: 1, minWidth: 320 }}>
                <h4>#{idx + 11} - {t.topicTitle.slice(0, 90)}</h4>
                <p><strong>Overall fit:</strong> {Math.round(t.overallFit)}/100</p>
                <p><strong>Recommendation:</strong> <span className="score">{t.recommendation}</span></p>
                <p><strong>Riassunto:</strong> <span className="small">{t.summary || 'N/A'}</span></p>
                <button onClick={() => openTopicDetail(t, idx + 10)}>Apri dettaglio call</button>
              </article>
            ))}
          </div>
        )}
      </div>

      <div className="pipeline-section" id="fit-selected-call">
        <h3>Dettaglio Call Selezionata</h3>
        {!selectedTopic ? (
          <p className="small">Seleziona una call dalla Top 10 o da "Altre Call" per vedere il dettaglio completo qui.</p>
        ) : (
          <>
            <h4>#{selectedTopic.rank} - {selectedTopic.topic.topicTitle}</h4>
            <p><strong>Recommendation:</strong> <span className="score">{selectedTopic.topic.recommendation}</span></p>
            <p><strong>Overall fit:</strong> {Math.round(selectedTopic.topic.overallFit)}/100</p>
            <p><strong>Summary:</strong> <span className="small">{selectedTopic.topic.summary}</span></p>
            <p><strong>Justification:</strong></p>
            <p className="small">{selectedTopic.topic.topicText}</p>
          </>
        )}
      </div>

      {fitLoading ? (
        <div
          className={`fit-loading-overlay${fitBooting ? ' is-booting' : ''}${fitFinishing ? ' is-finishing' : ''}${fitClosing ? ' is-outcome' : ''}${fitClosingExit ? ' is-closing' : ''}`}
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
                  <button onClick={onOpenTopCallFromOutcome}>Apri dettaglio Top Call</button>
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
