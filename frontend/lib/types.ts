export type HorizonMatcherScoreBreakdown = {
  fit_score: number;
  fit_score_100: number;
  weights: Record<string, number>;
  breakdown: Record<string, number>;
  optimal_contributions: Record<string, number>;
  status: string;
  cr: number;
  consistency_ok: boolean;
  constraints_applied: Record<string, unknown>;
  solver: string;
  local_scores: Record<string, number>;
};

export type HorizonMatcherCallData = {
  expected_outcomes?: string | null;
  scope?: string | null;
  budget_indicative?: string | null;
  deadline?: string | null;
  source_pages?: number[];
  source_document?: string | null;
  source_documents?: string[];
  specific_conditions?: Record<string, boolean>;
  trl_range?: string | null;
  trl_required?: number | null;
};

export type HorizonMatcherResult = {
  call_id: string;
  title: string;
  cluster: string | null;
  type_of_action: string | null;
  fit_score: number;
  fit_score_100: number;
  score_breakdown: HorizonMatcherScoreBreakdown;
  spider_axes: Record<string, number>;
  justification: string;
  explanation?: {
    ahp_detailed?: Record<string, unknown>;
    clear_explanation?: {
      testo_semplice?: string;
      citazioni_dirette?: string[];
      gap_principali?: string[];
      azioni_concrete?: string[];
      criterio_dominante?: string;
    };
    ai_fit_review?: {
      enabled?: boolean;
      provider?: string;
      model?: string | null;
      reasoning_enabled?: boolean;
      reasoning_available?: boolean;
      reasoning_preview?: string;
      reasoning_trace?: string;
      strategic_verdict?: string;
      qualitative_fit_label?: 'strong_fit' | 'conditional_fit' | 'weak_fit' | string;
      summary?: string;
      strengths?: string[];
      risks?: string[];
      next_steps?: string[];
      consortium_notes?: string[];
      ideal_role?: 'coordinator' | 'tech_partner' | 'end_user_partner' | 'watch_only' | string;
    };
    meta?: Record<string, unknown>;
  } | null;
  call_data?: HorizonMatcherCallData | null;
};

export type HorizonMatcherResponse = {
  generated_at: string;
  top_n: number;
  total_calls: number;
  results: HorizonMatcherResult[];
  other_results: HorizonMatcherResult[];
  status: Record<string, unknown>;
};

export type HorizonMatcherUploadResponse = {
  filename: string;
  files_processed?: number;
  calls_parsed: number;
  indexed_vectors: number;
  detected_cluster?: string | null;
  suggested_cluster_id?: string | null;
  cluster_distribution?: Record<string, number>;
  quality_summary?: Record<string, unknown>;
  status: Record<string, unknown>;
};

export type HorizonMatcherProfilePayload = {
  description: string;
  mission: string;
  technical_knowhow: string;
  keywords: string[];
  trl_current: number;
  budget_company_available: number;
  budget_max: number | null;
  is_sme: boolean;
  ssh_capacity: boolean;
  fair_compliant: boolean;
  gender_dimension_active: boolean;
  gender_balance_required: boolean;
  clusters_interest: string[];
};

export type HorizonMatcherExportPdfPayload = {
  clusterId: string;
  profile: HorizonMatcherProfilePayload;
  callIds?: string[] | null;
  include_all_calls?: boolean;
  top_n?: number;
  username?: string;
};
