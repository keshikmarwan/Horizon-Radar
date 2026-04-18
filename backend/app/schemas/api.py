from typing import Any

from pydantic import BaseModel, Field


class HorizonMatcherProfileIn(BaseModel):
    description: str
    mission: str
    technical_knowhow: str
    keywords: list[str] = Field(default_factory=list)
    trl_current: int = Field(default=5, ge=1, le=9)
    budget_company_available: float = 0.0
    budget_max: float | None = None
    is_sme: bool = False
    ssh_capacity: bool = False
    fair_compliant: bool = False
    gender_dimension_active: bool = False
    gender_balance_required: bool = False
    clusters_interest: list[str] = Field(default_factory=list)


class HorizonMatcherScoreIn(BaseModel):
    profile: HorizonMatcherProfileIn
    top_n: int = Field(default=10, ge=1, le=30)


class HorizonMatcherScoreBreakdownOut(BaseModel):
    fit_score: float
    fit_score_100: float
    weights: dict[str, float] = Field(default_factory=dict)
    breakdown: dict[str, float] = Field(default_factory=dict)
    optimal_contributions: dict[str, float] = Field(default_factory=dict)
    status: str
    cr: float
    consistency_ok: bool
    constraints_applied: dict[str, Any] = Field(default_factory=dict)
    solver: str
    local_scores: dict[str, float] = Field(default_factory=dict)


class HorizonMatcherResultOut(BaseModel):
    call_id: str
    title: str
    cluster: str | None = None
    type_of_action: str | None = None
    fit_score: float
    fit_score_100: float
    score_breakdown: HorizonMatcherScoreBreakdownOut
    spider_axes: dict[str, float]
    justification: str
    explanation: dict[str, Any] | None = None
    call_data: dict[str, Any] | None = None


class HorizonMatcherScoreOut(BaseModel):
    generated_at: str
    top_n: int
    total_calls: int
    results: list[HorizonMatcherResultOut]
    other_results: list[HorizonMatcherResultOut]
    status: dict[str, Any]


class HorizonMatcherUploadOut(BaseModel):
    filename: str
    files_processed: int = 1
    calls_parsed: int
    indexed_vectors: int
    detected_cluster: str | None = None
    suggested_cluster_id: str | None = None
    cluster_distribution: dict[str, int] = Field(default_factory=dict)
    quality_summary: dict[str, Any] = Field(default_factory=dict)
    status: dict[str, Any]


class HorizonMatcherExportPdfIn(BaseModel):
    clusterId: str
    profile: HorizonMatcherProfileIn
    callIds: list[str] | None = None
    include_all_calls: bool = False
    top_n: int = Field(default=15, ge=1, le=100)
    username: str | None = None
