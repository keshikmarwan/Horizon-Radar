export type HorizonMatcherScoreBreakdown = {
  impact_match: number;
  technical_match: number;
  semantic_score: number;
  bm25_score: number;
  bm25_boost_applied: boolean;
  trl_score: number;
  eligibility_score: number;
  constraints_score: number;
  weights_used: Record<string, number>;
};

export type HorizonMatcherResult = {
  call_id: string;
  title: string;
  cluster: string | null;
  type_of_action: string | null;
  reliability_score: number;
  score_breakdown: HorizonMatcherScoreBreakdown;
  spider_axes: Record<string, number>;
  justification: string;
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
  calls_parsed: number;
  indexed_vectors: number;
  detected_cluster?: string | null;
  suggested_cluster_id?: string | null;
  cluster_distribution?: Record<string, number>;
  status: Record<string, unknown>;
};
