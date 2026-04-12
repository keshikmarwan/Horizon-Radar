export type Profile = {
  id: number;
  user_id: string;
  name: string;
  description: string;
  tags: string[];
  constraints: Record<string, unknown>;
};

export type Topic = {
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
};

export type TopicFit = {
  topic_id: number;
  profile_id: number;
  adjusted_score: number;
  recommendation: string;
  gaps: string;
  evidence_snippets: string[];
  suggested_partner_types: string[];
};

export type MatchResultV2 = {
  id: number;
  profile_id: number;
  topic_id: number;
  eligibility_fit: number;
  thematic_fit: number;
  impact_fit: number;
  implementation_fit: number;
  consortium_fit: number;
  data_ai_fit: number;
  evidence_strength: number;
  overall_fit: number;
  gap_score: number;
  readiness_score: number;
  partner_dependency_score: number;
  submission_priority: number;
  confidence: number;
  recommendation: string;
  recommended_role: string;
  model_version: string;
  generated_at: string;
};

export type MatchRecomputeV2Response = {
  profile_id: number;
  model_version: string;
  evaluated_topics: number;
  matches_inserted: number;
  matches_skipped_by_hard_filters: number;
  groq_coverage_count?: number | null;
  groq_coverage_total?: number | null;
  groq_coverage_pct?: number | null;
  top_topics: Array<{
    topic_db_id: number;
    submission_priority: number;
    overall_fit: number;
    recommendation: string;
  }>;
};

export type TopicDecisionCardV2 = {
  profile_id: number;
  topic_id: number;
  topic_code: string;
  title: string;
  recommendation: string;
  recommended_role: string;
  overall_fit: number;
  gap_score: number;
  readiness_score: number;
  partner_dependency_score: number;
  submission_priority: number;
  confidence: number;
  dimensions: Record<string, number>;
  why_fit: string[];
  why_not_fit: string[];
  must_have_gaps: string[];
  nice_to_have_gaps: string[];
  suggested_partner_types: string[];
  suggested_actions: string[];
};

export type Report = {
  id: number;
  user_id: string;
  report_month: string;
  html_path: string;
  pdf_path: string | null;
  summary: string;
};

export type Draft = {
  id: number;
  source: string;
  title: string;
  source_url: string;
  file_url: string | null;
  version_label: string | null;
  diff_summary: string | null;
  discovered_at: string;
};

export type ReportDraftItem = {
  source: string;
  title: string;
  link: string;
  file_url: string | null;
};

export type BrokerageEvent = {
  title: string;
  link: string;
  date: string | null;
  location: string | null;
  source: string | null;
};

export type DeadlineAlert = {
  source: string;
  title: string;
  topic_id: string;
  deadline: string;
  status: string | null;
  link: string | null;
  explanation: string;
};

export type ReportAssistantResponse = {
  answer: string;
  sources: Array<Record<string, unknown>>;
};
