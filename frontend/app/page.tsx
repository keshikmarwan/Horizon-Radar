'use client';

import Link from 'next/link';
import { ChangeEvent, DragEvent, useCallback, useEffect, useMemo, useState } from 'react';
import {
  CLUSTERS,
  ClusterData,
  ClusterId,
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
import { apiPostFormData } from '@/lib/api';
import {
  DashboardOverview,
  DecisionReport,
  PipelineStage,
  fetchDashboardOverviewV2,
  fetchDecisionReportV2,
  saveWorkflow,
} from '@/lib/services/dashboard';

type Opportunity = {
  id: string;
  profileId: number;
  topicDbId: number;
  topicId: string;
  profileName: string;
  title: string;
  cluster: string | null;
  fitScore: number;
  trl: string | null;
  budget: string | null;
  deadline: string | null;
  stage: PipelineStage;
  nextAction: string;
  procedureStage: string | null;
  complianceFlags: string[];
  priority: string | null;
  owner: string;
  notes: string;
};

export default function DashboardPage() {
  const [clusterData, setClusterData] = useState<Partial<Record<ClusterId, ClusterData>>>({});
  const [instances, setInstances] = useState<ClusterInstanceMeta[]>([]);
  const [activeInstanceId, setActiveInstanceId] = useState('');
  const [isHydrated, setIsHydrated] = useState(false);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState('');
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [workflowSavingId, setWorkflowSavingId] = useState<string | null>(null);
  const [dragOpportunityId, setDragOpportunityId] = useState<string | null>(null);
  const [workflowDrafts, setWorkflowDrafts] = useState<Record<string, {
    stage: PipelineStage;
    priority: string;
    owner: string;
    notes: string;
  }>>({});
  const [opportunityFilter, setOpportunityFilter] = useState<'all' | 'my-priorities'>('all');
  const [report, setReport] = useState<DecisionReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  const uploadedClusters = useMemo(
    () => CLUSTERS.filter((c) => Boolean(clusterData[c]?.fileName)),
    [clusterData],
  );
  const activeInstance = instances.find((x) => x.id === activeInstanceId) || null;
  const profileCount = uploadedClusters.length;

  const stageCounts = useMemo(() => {
    const base: Record<PipelineStage, number> = { Scouting: 0, Valutazione: 0, Draft: 0, Submitted: 0 };
    if (!overview) return base;
    for (const item of overview.pipeline) {
      base[item.stage] = item.count;
    }
    return base;
  }, [overview]);

  const nearestDeadlineDays = useMemo(() => {
    return overview?.kpis.nearest_deadline_days ?? 0;
  }, [overview]);

  const averageFit = useMemo(() => {
    return overview?.kpis.average_fit ?? 0;
  }, [overview]);

  const criticalRiskCount = useMemo(
    () => overview?.kpis.critical_risks ?? 0,
    [overview],
  );

  useEffect(() => {
    const ctx = ensureClusterWorkspace();
    setActiveInstanceId(ctx.instanceId);
    setInstances(ctx.instances);
    setClusterData(ctx.store.clusterData);
    setIsHydrated(true);
  }, []);

  const syncOverview = useCallback(async () => {
    setDashboardLoading(true);
    setDashboardError('');
    try {
      const data = await fetchDashboardOverviewV2(12, 'v2-sprint1');
      setOverview(data);
      setOpportunities(
        data.opportunities.map((item) => ({
          id: item.id,
          profileId: item.profile_id,
          topicDbId: item.topic_db_id,
          topicId: item.topic_id,
          profileName: item.profile_name,
          title: item.title,
          cluster: item.cluster,
          fitScore: item.fit_score,
          trl: item.trl,
          budget: item.budget,
          deadline: item.deadline,
          stage: item.workflow?.stage || item.stage,
          nextAction: item.next_action,
          procedureStage: item.procedure_stage,
          complianceFlags: item.compliance_flags || [],
          priority: item.workflow?.priority || null,
          owner: item.workflow?.owner || '',
          notes: item.workflow?.notes || '',
        })),
      );
    } catch (err) {
      setOverview(null);
      setOpportunities([]);
      setDashboardError(err instanceof Error ? err.message : String(err));
    } finally {
      setDashboardLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    void syncOverview();
  }, [isHydrated, syncOverview]);

  useEffect(() => {
    if (!isHydrated || !activeInstanceId) return;
    writeClusterStore({ clusterData }, activeInstanceId);
    setInstances(listClusterInstances());
  }, [clusterData, isHydrated, activeInstanceId]);

  useEffect(() => {
    const next: Record<string, { stage: PipelineStage; priority: string; owner: string; notes: string }> = {};
    for (const item of opportunities) {
      next[item.id] = {
        stage: item.stage,
        priority: item.priority || '',
        owner: item.owner || '',
        notes: item.notes || '',
      };
    }
    setWorkflowDrafts(next);
  }, [opportunities]);

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
    setInstances(listClusterInstances());
  };

  const onChangeInstance = (instanceId: string) => {
    setActiveInstanceId(instanceId);
    const store = switchClusterInstance(instanceId);
    setClusterData(store.clusterData);
    setInstances(listClusterInstances());
  };

  const onDeleteInstance = () => {
    if (!activeInstanceId) return;
    const ok = window.confirm(`Eliminare l'istanza "${activeInstance?.name || activeInstanceId}"?`);
    if (!ok) return;
    const result = deleteClusterInstance(activeInstanceId);
    setActiveInstanceId(result.instanceId);
    setClusterData(result.store.clusterData);
    setInstances(result.instances);
  };

  const onFileUpload = async (cluster: ClusterId, event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    let fileText = '';
    let extractedBy = '';
    let extractedChars = 0;
    let extractionError = '';
    try {
      const formData = new FormData();
      formData.append('file', file);
      const extracted = await apiPostFormData<{ text: string; extracted_by?: string; chars?: number }>('/api/extract-text', formData);
      fileText = (extracted.text || '').slice(0, 600000);
      extractedBy = extracted.extracted_by || 'backend';
      extractedChars = extracted.chars || fileText.length;
      if (!fileText) extractionError = 'Estrazione completata ma testo vuoto.';
    } catch (err) {
      extractionError = `Errore estrazione backend (/api/extract-text): ${err instanceof Error ? err.message : String(err)}`;
      const isTextLike =
        file.type.includes('text') ||
        file.name.endsWith('.doc') ||
        file.name.endsWith('.docx') ||
        file.name.endsWith('.txt') ||
        file.name.endsWith('.md') ||
        file.name.endsWith('.csv') ||
        file.name.endsWith('.json');
      if (isTextLike) {
        fileText = (await file.text()).slice(0, 300000);
        extractedBy = 'frontend-text-fallback';
        extractedChars = fileText.length;
      }
    }

    setClusterData((prev) => ({
      ...prev,
      [cluster]: {
        fileName: file.name,
        fileType: file.type || 'application/octet-stream',
        uploadedAt: new Date().toISOString(),
        fileText,
        extractedBy,
        extractedChars,
        extractionError,
        companyDescription: prev[cluster]?.companyDescription || '',
        clusterInterests: prev[cluster]?.clusterInterests || '',
      },
    }));
  };

  const removeClusterFile = (cluster: ClusterId) => {
    const current = clusterData[cluster];
    if (!current?.fileName) return;
    const ok = window.confirm(`Rimuovere il file caricato per ${cluster}?`);
    if (!ok) return;

    setClusterData((prev) => {
      const existing = prev[cluster];
      if (!existing) return prev;
      return {
        ...prev,
        [cluster]: {
          ...existing,
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
  };

  const clearWorkspace = () => {
    setClusterData({});
    if (activeInstanceId) {
      writeClusterStore({ clusterData: {} }, activeInstanceId);
    }
  };

  const timelineItems = useMemo(
    () => (overview?.roadmap || []).map((item) => ({ label: item.label, days: item.days_remaining })),
    [overview],
  );

  const formatDeadline = (isoDate: string | null) => {
    if (!isoDate) return 'n/d';
    const d = new Date(isoDate);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' });
  };

  const updateWorkflowDraft = (
    itemId: string,
    patch: Partial<{ stage: PipelineStage; priority: string; owner: string; notes: string }>,
  ) => {
    setWorkflowDrafts((prev) => ({
      ...prev,
      [itemId]: {
        stage: patch.stage ?? prev[itemId]?.stage ?? 'Scouting',
        priority: patch.priority ?? prev[itemId]?.priority ?? '',
        owner: patch.owner ?? prev[itemId]?.owner ?? '',
        notes: patch.notes ?? prev[itemId]?.notes ?? '',
      },
    }));
  };

  const saveOpportunityWorkflow = async (item: Opportunity) => {
    const draft = workflowDrafts[item.id];
    if (!draft) return;
    try {
      setWorkflowSavingId(item.id);
      await saveWorkflow({
        profile_id: item.profileId,
        topic_db_id: item.topicDbId,
        stage: draft.stage,
        priority: draft.priority || null,
        owner: draft.owner || null,
        notes: draft.notes || null,
      });
      await syncOverview();
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorkflowSavingId(null);
    }
  };

  const visibleOpportunities = useMemo(() => {
    if (opportunityFilter === 'all') return opportunities;
    return opportunities.filter((item) => {
      const draft = workflowDrafts[item.id];
      const priority = (draft?.priority || item.priority || '').toLowerCase();
      return priority === 'high' || priority === 'critical';
    });
  }, [opportunities, opportunityFilter, workflowDrafts]);

  const opportunitiesByStage = useMemo(() => {
    const grouped: Record<PipelineStage, Opportunity[]> = {
      Scouting: [],
      Valutazione: [],
      Draft: [],
      Submitted: [],
    };
    for (const item of opportunities) {
      const stage = (workflowDrafts[item.id]?.stage || item.stage) as PipelineStage;
      grouped[stage].push(item);
    }
    return grouped;
  }, [opportunities, workflowDrafts]);

  const onDragStartOpportunity = (opportunityId: string) => {
    setDragOpportunityId(opportunityId);
  };

  const onDropOnStage = async (stage: PipelineStage) => {
    if (!dragOpportunityId) return;
    const item = opportunities.find((x) => x.id === dragOpportunityId);
    if (!item) {
      setDragOpportunityId(null);
      return;
    }
    updateWorkflowDraft(item.id, { stage });
    try {
      setWorkflowSavingId(item.id);
      await saveWorkflow({
        profile_id: item.profileId,
        topic_db_id: item.topicDbId,
        stage,
        priority: workflowDrafts[item.id]?.priority || item.priority || null,
        owner: workflowDrafts[item.id]?.owner || item.owner || null,
        notes: workflowDrafts[item.id]?.notes || item.notes || null,
      });
      await syncOverview();
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorkflowSavingId(null);
      setDragOpportunityId(null);
    }
  };

  const generateDecisionReport = async () => {
    try {
      setReportLoading(true);
      const data = await fetchDecisionReportV2(12, 'v2-sprint1');
      setReport(data);
    } catch (err) {
      setDashboardError(err instanceof Error ? err.message : String(err));
    } finally {
      setReportLoading(false);
    }
  };

  const copyDecisionReport = async () => {
    if (!report?.markdown) return;
    try {
      await navigator.clipboard.writeText(report.markdown);
    } catch {
      setDashboardError('Copia report non riuscita.');
    }
  };

  return (
    <>
      <section className="landing-hero rd-hero" aria-labelledby="landing-title">
        <div className="landing-container">
          <div className="rd-hero-grid">
            <div>
              <p className="landing-eyebrow">R&D Decision Cockpit</p>
              <h1 id="landing-title">Prioritizza call, riduci il rischio, accelera submission.</h1>
              <p className="landing-subtitle">
                Workspace operativo per R&D manager: visione KPI, pipeline proposta, controllo scadenze e next action.
              </p>
              <div className="landing-cta">
                <a href="#opportunities" className="link-btn">Vedi Opportunita</a>
                <a href="#workspace" className="link-btn">Apri Workspace</a>
                <Link href="/profiles" className="link-btn">Gestisci Profiles</Link>
              </div>
            </div>
            <div className="rd-timeline-card">
              <h3>Roadmap proposta</h3>
              <p className="small">Punti di controllo chiave prima della deadline piu vicina.</p>
              <div className="rd-timeline-list">
                {timelineItems.length === 0 ? (
                  <p className="small">Nessuna roadmap disponibile. Esegui un fit per popolare le scadenze.</p>
                ) : (
                  timelineItems.map((item) => (
                    <div key={item.label} className="rd-timeline-item">
                      <div className="rd-timeline-dot" />
                      <div>
                        <div className="rd-timeline-label">{item.label}</div>
                        <div className="small">T-{item.days} giorni</div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="section section--tight rd-zone rd-zone--decision" aria-label="KPI Overview">
        <div className="landing-container">
          <p className="rd-zone-label">Decision Layer</p>
          <div className="rd-kpi-grid">
            <article className="rd-kpi-card">
              <div className="rd-kpi-label">Opportunita attive</div>
              <div className="rd-kpi-value">{overview?.kpis.active_opportunities ?? 0}</div>
              <div className="small">Portafoglio corrente</div>
            </article>
            <article className="rd-kpi-card">
              <div className="rd-kpi-label">Fit medio</div>
              <div className="rd-kpi-value">{averageFit}%</div>
              <div className="small">Media cluster-topic</div>
            </article>
            <article className="rd-kpi-card">
              <div className="rd-kpi-label">Deadline piu vicina</div>
              <div className="rd-kpi-value">{nearestDeadlineDays > 0 ? `${nearestDeadlineDays}g` : '-'}</div>
              <div className="small">Finestra proposta residua</div>
            </article>
            <article className="rd-kpi-card">
              <div className="rd-kpi-label">Rischi critici</div>
              <div className="rd-kpi-value">{criticalRiskCount}</div>
              <div className="small">Da riesaminare oggi</div>
            </article>
          </div>
        </div>
      </section>

      <section className="section section--tight rd-zone-sub" aria-label="Pipeline Status">
        <div className="landing-container">
          <h2 className="landing-title">Pipeline proposta</h2>
          <p className="landing-copy">Distribuzione rapida delle opportunita per stato operativo.</p>
          {dashboardError ? <p className="small">Errore caricamento dati: {dashboardError}</p> : null}
          {dashboardLoading ? <p className="small">Aggiornamento dati operativi...</p> : null}
          <div className="rd-pipeline-grid">
            {(['Scouting', 'Valutazione', 'Draft', 'Submitted'] as PipelineStage[]).map((stage) => (
              <article key={stage} className="rd-pipeline-card">
                <div className="rd-pipeline-stage">{stage}</div>
                <div className="rd-pipeline-count">{stageCounts[stage]}</div>
                <div className="small">item in coda</div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="section section--tight rd-zone-sub" aria-label="Workflow Kanban">
        <div className="landing-container">
          <h2 className="landing-title">Workflow Kanban</h2>
          <p className="landing-copy">Trascina le opportunita tra colonne per aggiornare lo stage operativo.</p>
          <div className="rd-pipeline-grid">
            {(['Scouting', 'Valutazione', 'Draft', 'Submitted'] as PipelineStage[]).map((stage) => (
              <article
                key={`kanban-${stage}`}
                className="rd-pipeline-card"
                onDragOver={(e: DragEvent<HTMLElement>) => e.preventDefault()}
                onDrop={() => { void onDropOnStage(stage); }}
                style={{ minHeight: 220 }}
              >
                <div className="rd-pipeline-stage">{stage}</div>
                <div className="small" style={{ marginTop: '0.4rem' }}>{opportunitiesByStage[stage].length} item</div>
                <div style={{ marginTop: '0.8rem', display: 'grid', gap: '0.6rem' }}>
                  {opportunitiesByStage[stage].slice(0, 5).map((item) => (
                    <div
                      key={`kanban-item-${item.id}`}
                      draggable
                      onDragStart={() => onDragStartOpportunity(item.id)}
                      className="rd-meta-pill"
                      style={{ cursor: 'grab' }}
                    >
                      {item.topicId} • {item.fitScore}%
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="opportunities" className="section section--tight rd-zone-sub" aria-label="Opportunity Cards">
        <div className="landing-container">
          <h2 className="landing-title">Opportunity Board</h2>
          <p className="landing-copy">Ogni card include fit, budget, TRL, deadline e prossima azione decisionale.</p>
          <div className="row" style={{ marginTop: '0.8rem', marginBottom: '0.8rem' }}>
            <button
              onClick={() => setOpportunityFilter('all')}
              className={opportunityFilter === 'all' ? 'link-btn' : ''}
            >
              Tutte
            </button>
            <button
              onClick={() => setOpportunityFilter('my-priorities')}
              className={opportunityFilter === 'my-priorities' ? 'link-btn' : ''}
            >
              My priorities
            </button>
          </div>
          <div className="rd-opportunity-grid">
            {visibleOpportunities.length === 0 ? (
              <article className="rd-opportunity-card">
                <p className="small">
                  {opportunityFilter === 'my-priorities'
                    ? 'Nessuna opportunita in priorita alta/critica.'
                    : 'Nessuna opportunita disponibile. Crea un profilo e avvia il fit su un cluster.'}
                </p>
              </article>
            ) : (
              visibleOpportunities.map((item) => (
                <article key={item.id} className="rd-opportunity-card">
                  <div className="rd-opportunity-top">
                    <p className="small">{item.cluster || 'N/D'} • {item.stage}</p>
                    <span className="score">{item.fitScore}% fit</span>
                  </div>
                  <h3>{item.title}</h3>
                  <p className="small">Topic: {item.topicId} • Profile: {item.profileName}</p>
                  <div className="rd-metadata-row">
                    <span className="rd-meta-pill">{item.trl ? `TRL ${item.trl}` : 'TRL n/d'}</span>
                    <span className="rd-meta-pill">{item.budget || 'Budget n/d'}</span>
                    <span className="rd-meta-pill">Deadline {formatDeadline(item.deadline)}</span>
                    {item.procedureStage ? <span className="rd-meta-pill">{item.procedureStage}</span> : null}
                  </div>
                  {item.complianceFlags.length > 0 ? (
                    <p className="small">Compliance: {item.complianceFlags.slice(0, 4).join(', ')}</p>
                  ) : null}
                  <p className="small">{item.nextAction}</p>
                  <div className="row">
                    <label className="small" htmlFor={`stage-${item.id}`}>Workflow</label>
                    <select
                      id={`stage-${item.id}`}
                      value={workflowDrafts[item.id]?.stage || item.stage}
                      onChange={(e) => updateWorkflowDraft(item.id, { stage: e.target.value as PipelineStage })}
                      disabled={workflowSavingId === item.id}
                      style={{ minWidth: 200 }}
                    >
                      <option value="Scouting">Scouting</option>
                      <option value="Valutazione">Valutazione</option>
                      <option value="Draft">Draft</option>
                      <option value="Submitted">Submitted</option>
                    </select>
                  </div>
                  <div className="row">
                    <label className="small" htmlFor={`priority-${item.id}`}>Priority</label>
                    <select
                      id={`priority-${item.id}`}
                      value={workflowDrafts[item.id]?.priority || ''}
                      onChange={(e) => updateWorkflowDraft(item.id, { priority: e.target.value })}
                      disabled={workflowSavingId === item.id}
                      style={{ minWidth: 200 }}
                    >
                      <option value="">None</option>
                      <option value="low">Low</option>
                      <option value="medium">Medium</option>
                      <option value="high">High</option>
                      <option value="critical">Critical</option>
                    </select>
                  </div>
                  <div className="row">
                    <label className="small" htmlFor={`owner-${item.id}`}>Owner</label>
                    <input
                      id={`owner-${item.id}`}
                      value={workflowDrafts[item.id]?.owner || ''}
                      onChange={(e) => updateWorkflowDraft(item.id, { owner: e.target.value })}
                      disabled={workflowSavingId === item.id}
                      placeholder="Responsabile opportunita"
                    />
                  </div>
                  <div className="row">
                    <label className="small" htmlFor={`notes-${item.id}`}>Notes</label>
                    <textarea
                      id={`notes-${item.id}`}
                      value={workflowDrafts[item.id]?.notes || ''}
                      onChange={(e) => updateWorkflowDraft(item.id, { notes: e.target.value })}
                      disabled={workflowSavingId === item.id}
                      placeholder="Note operative, rischi, prossimo checkpoint..."
                      rows={3}
                    />
                  </div>
                  <div className="row">
                    <button onClick={() => { void saveOpportunityWorkflow(item); }} disabled={workflowSavingId === item.id}>
                      {workflowSavingId === item.id ? 'Salvataggio...' : 'Salva Workflow'}
                    </button>
                  </div>
                  <div className="row">
                    {item.cluster && CLUSTERS.includes(item.cluster as ClusterId) ? (
                      <Link className="link-btn" href={`/cluster/${item.cluster as ClusterId}`}>Apri cluster</Link>
                    ) : null}
                    <Link className="link-btn" href="/reports">Valuta report</Link>
                  </div>
                </article>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="section section--tight rd-zone-sub" aria-label="Compliance risk">
        <div className="landing-container">
          <h2 className="landing-title">Compliance Risk Board</h2>
          <p className="landing-copy">Rischi ricorrenti estratti dai topic in pipeline (eligibility, ethics, regulatory, data).</p>
          <div className="rd-metadata-row" style={{ marginTop: '1rem' }}>
            {(overview?.compliance_risks || []).length === 0 ? (
              <p className="small">Nessun rischio compliance rilevato.</p>
            ) : (
              (overview?.compliance_risks || []).map((risk) => (
                <span key={risk.flag} className="rd-meta-pill">{risk.flag}: {risk.count}</span>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="section section--tight rd-zone-sub" aria-label="Alert center">
        <div className="landing-container">
          <h2 className="landing-title">Alert Center</h2>
          <p className="landing-copy">Alert operativi su deadline, ownership e compliance.</p>
          <div className="rd-opportunity-grid">
            {(overview?.alerts || []).length === 0 ? (
              <article className="rd-opportunity-card">
                <p className="small">Nessun alert attivo.</p>
              </article>
            ) : (
              (overview?.alerts || []).map((alert, index) => (
                <article key={`alert-${index}`} className="rd-opportunity-card">
                  <div className="rd-opportunity-top">
                    <p className="small">{alert.topic_id || 'GLOBAL'}</p>
                    <span className="score">{alert.level.toUpperCase()}</span>
                  </div>
                  <h3>{alert.title}</h3>
                  <p className="small">{alert.detail}</p>
                </article>
              ))
            )}
          </div>
        </div>
      </section>

      <section className="section section--tight rd-zone-sub" aria-label="Decision report">
        <div className="landing-container">
          <h2 className="landing-title">Decision Report</h2>
          <p className="landing-copy">Genera un report sintetico pronto per management meeting.</p>
          <div className="row" style={{ marginTop: '1rem' }}>
            <button onClick={() => { void generateDecisionReport(); }} disabled={reportLoading}>
              {reportLoading ? 'Generazione...' : 'Genera Report'}
            </button>
            <button onClick={() => { void copyDecisionReport(); }} disabled={!report?.markdown}>
              Copia Markdown
            </button>
          </div>
          {report?.generated_at ? (
            <p className="small">Aggiornato: {new Date(report.generated_at).toLocaleString('it-IT')}</p>
          ) : null}
          {report?.markdown ? (
            <textarea
              readOnly
              value={report.markdown}
              rows={14}
              style={{ width: '100%', marginTop: '0.8rem' }}
            />
          ) : (
            <p className="small" style={{ marginTop: '0.8rem' }}>Nessun report generato.</p>
          )}
        </div>
      </section>

      <section id="workspace" className="section section--tight workspace-section rd-zone rd-zone--execution" aria-label="Workspace operativo">
        <div className="landing-container">
          <p className="rd-zone-label">Execution Layer</p>
          <div className="landing-grid">
            <article className="landing-card">
              <h3>Workspace Istanze</h3>
              <p className="small">Versiona scenari R&D e passa da un piano all'altro in modo tracciabile.</p>
              <div className="row">
                <button onClick={saveInstance}>Salva</button>
                <button onClick={saveAndCreateNewInstance}>Nuova istanza</button>
                <button className="btn-danger" onClick={onDeleteInstance}>Elimina</button>
                <select value={activeInstanceId} onChange={(e) => onChangeInstance(e.target.value)} style={{ minWidth: 280 }}>
                  {instances.map((inst) => (
                    <option key={inst.id} value={inst.id}>
                      {inst.name} ({new Date(inst.updatedAt).toLocaleString()})
                    </option>
                  ))}
                </select>
              </div>
            </article>

            <article className="landing-card">
              <h3>Quick Actions</h3>
              <p className="small">Azioni rapide per reset operativo e apertura diretta dei cluster prioritari.</p>
              <div className="row">
                <button className="btn-danger" onClick={clearWorkspace}>Svuota Workspace</button>
                {uploadedClusters.map((cluster) => (
                  <Link className="link-btn" key={`quick-${cluster}`} href={`/cluster/${cluster}`}>
                    Apri {cluster}
                  </Link>
                ))}
                {uploadedClusters.length === 0 ? <span className="small">Nessun cluster caricato.</span> : null}
              </div>
              <p className="small" style={{ marginTop: '0.8rem' }}>Profiles attivi: {profileCount} • Istanze: {instances.length}</p>
            </article>
          </div>
        </div>
      </section>

      <section className="section feature-alt rd-zone-sub" aria-label="Upload area">
        <div className="landing-container">
          <div className="feature-wrap">
            <div className="feature-copy">
              <h2 className="landing-title">Ingestion documentale per cluster.</h2>
              <p className="landing-copy">
                Carica fonti tecniche e requisiti per CL1-CL6, con estrazione testo automatica e aggancio al matching.
              </p>
            </div>
            <div className="feature-panel">
              <div className="upload-grid">
                {CLUSTERS.map((cluster) => (
                  <article key={cluster} className="card upload-slot">
                    <strong>{cluster}</strong>
                    <label className="file-input-modern">
                      <input
                        type="file"
                        onChange={(e) => { void onFileUpload(cluster, e); }}
                      />
                      <span>Carica file</span>
                    </label>
                    <p className="small" style={{ marginTop: '0.6rem' }}>
                      {clusterData[cluster] ? `File: ${clusterData[cluster]?.fileName}` : 'Nessun file caricato'}
                    </p>
                    {clusterData[cluster]?.fileName ? (
                      <div className="row" style={{ marginTop: '0.5rem' }}>
                        <button className="btn-danger" onClick={() => removeClusterFile(cluster)} type="button">
                          Rimuovi file
                        </button>
                      </div>
                    ) : null}
                    {clusterData[cluster]?.extractedBy ? (
                      <p className="small">Extract: {clusterData[cluster]?.extractedBy} ({clusterData[cluster]?.extractedChars || 0} chars)</p>
                    ) : null}
                    {clusterData[cluster]?.extractionError ? (
                      <p className="small">{clusterData[cluster]?.extractionError}</p>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
