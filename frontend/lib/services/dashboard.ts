import { apiGet, apiPatch } from '@/lib/api';

export type PipelineStage = 'Scouting' | 'Valutazione' | 'Draft' | 'Submitted';

export type DashboardOverview = {
  kpis: {
    active_opportunities: number;
    average_fit: number;
    nearest_deadline_days: number | null;
    critical_risks: number;
  };
  pipeline: Array<{ stage: PipelineStage; count: number }>;
  opportunities: Array<{
    id: string;
    profile_id: number;
    topic_db_id: number;
    topic_id: string;
    profile_name: string;
    title: string;
    cluster: string | null;
    fit_score: number;
    stage: PipelineStage;
    trl: string | null;
    budget: string | null;
    deadline: string | null;
    next_action: string;
    procedure_stage: string | null;
    compliance_flags: string[];
    workflow?: {
      id: number;
      stage: PipelineStage;
      priority?: string | null;
      owner?: string | null;
      notes?: string | null;
      updated_at: string;
    } | null;
  }>;
  compliance_risks: Array<{ flag: string; count: number }>;
  alerts: Array<{ level: string; title: string; detail: string; topic_id?: string | null }>;
  roadmap: Array<{ label: string; days_remaining: number; priority: string }>;
  generated_at: string;
};

export type DecisionReport = {
  markdown: string;
  generated_at: string;
};

export async function fetchDashboardOverviewV2(limit = 12, modelVersion = 'v2-sprint1'): Promise<DashboardOverview> {
  return apiGet<DashboardOverview>(
    `/api/v2/dashboard/overview?limit=${limit}&model_version=${encodeURIComponent(modelVersion)}`
  );
}

export async function fetchDecisionReportV2(limit = 12, modelVersion = 'v2-sprint1'): Promise<DecisionReport> {
  return apiGet<DecisionReport>(
    `/api/v2/dashboard/decision-report?limit=${limit}&model_version=${encodeURIComponent(modelVersion)}`
  );
}

export async function saveWorkflow(payload: {
  profile_id: number;
  topic_db_id: number;
  stage: PipelineStage;
  priority?: string | null;
  owner?: string | null;
  notes?: string | null;
}): Promise<void> {
  await apiPatch('/api/workflows', payload);
}
