from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProfileCreate(BaseModel):
    user_id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class ProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    constraints: dict[str, Any] | None = None


class ProfileOut(BaseModel):
    id: int
    user_id: str
    name: str
    description: str
    tags: list[str]
    constraints: dict[str, Any]

    class Config:
        from_attributes = True


class TopicOut(BaseModel):
    id: int
    topic_id: str
    title: str
    cluster: str | None
    action_type: str | None
    trl_min: int | None
    trl_max: int | None
    budget_total: float | None
    deadline: datetime | None
    status: str | None
    topic_url: str | None
    adjusted_score: float | None = None
    procedure_stage: str | None = None
    compliance_flags: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TopicDetailOut(TopicOut):
    expected_outcomes: str | None
    scope: str | None
    metadata_json: dict


class MatchOut(BaseModel):
    topic_id: int
    semantic_score: float
    adjusted_score: float
    recommendation: str
    gaps: str
    evidence_snippets: list[str]

    class Config:
        from_attributes = True


class TopicFitOut(BaseModel):
    topic_id: int
    profile_id: int
    adjusted_score: float
    recommendation: str
    gaps: str
    evidence_snippets: list[str]
    suggested_partner_types: list[str]


class DraftOut(BaseModel):
    id: int
    source: str
    title: str
    source_url: str
    file_url: str | None
    version_label: str | None
    diff_summary: str | None
    discovered_at: datetime

    class Config:
        from_attributes = True


class WorkProgrammeTextIn(BaseModel):
    text: str
    cluster: str | None = 'CL1'
    profile_id: int | None = None
    auto_match: bool = False


class DashboardKpiOut(BaseModel):
    active_opportunities: int
    average_fit: int
    nearest_deadline_days: int | None = None
    critical_risks: int


class DashboardPipelineOut(BaseModel):
    stage: str
    count: int


class DashboardWorkflowStateOut(BaseModel):
    id: int
    stage: str
    priority: str | None = None
    owner: str | None = None
    notes: str | None = None
    updated_at: datetime


class DashboardOpportunityOut(BaseModel):
    id: str
    profile_id: int
    topic_db_id: int
    topic_id: str
    title: str
    profile_name: str
    cluster: str | None = None
    fit_score: int
    stage: str
    trl: str | None = None
    budget: str | None = None
    deadline: datetime | None = None
    next_action: str
    procedure_stage: str | None = None
    compliance_flags: list[str] = Field(default_factory=list)
    workflow: DashboardWorkflowStateOut | None = None


class DashboardRiskOut(BaseModel):
    flag: str
    count: int


class DashboardAlertOut(BaseModel):
    level: str
    title: str
    detail: str
    topic_id: str | None = None


class DashboardRoadmapTaskOut(BaseModel):
    label: str
    days_remaining: int
    priority: str


class DashboardOverviewOut(BaseModel):
    kpis: DashboardKpiOut
    pipeline: list[DashboardPipelineOut]
    opportunities: list[DashboardOpportunityOut]
    compliance_risks: list[DashboardRiskOut]
    alerts: list[DashboardAlertOut]
    roadmap: list[DashboardRoadmapTaskOut]
    generated_at: datetime


class OpportunityWorkflowUpsertIn(BaseModel):
    profile_id: int
    topic_db_id: int
    stage: str
    priority: str | None = None
    owner: str | None = None
    notes: str | None = None


class OpportunityWorkflowOut(BaseModel):
    id: int
    user_id: str
    profile_id: int
    topic_id: int
    stage: str
    priority: str | None = None
    owner: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DecisionReportOut(BaseModel):
    markdown: str
    generated_at: datetime


class MatchRecomputeV2In(BaseModel):
    profile_id: int
    model_version: str = 'v2-sprint1'
    limit_topics: int | None = Field(default=None, ge=1, le=1000)


class MatchRecomputeV2TopicOut(BaseModel):
    topic_db_id: int
    submission_priority: float
    overall_fit: float
    recommendation: str


class MatchRecomputeV2Out(BaseModel):
    profile_id: int
    model_version: str
    evaluated_topics: int
    matches_inserted: int
    matches_skipped_by_hard_filters: int
    top_topics: list[MatchRecomputeV2TopicOut]


class ProfileCapabilityIn(BaseModel):
    name: str
    description: str
    domain_tags: list[str] = Field(default_factory=list)
    maturity_level: str | None = None
    keywords: list[str] = Field(default_factory=list)


class ProfileCapabilityOut(BaseModel):
    id: int
    profile_id: int
    name: str
    description: str
    domain_tags: list[str]
    maturity_level: str | None = None
    keywords: list[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProfileEvidenceIn(BaseModel):
    evidence_type: str
    title: str
    summary: str
    year: int | None = None
    partners: list[str] = Field(default_factory=list)
    outcomes: str | None = None


class ProfileEvidenceOut(BaseModel):
    id: int
    profile_id: int
    evidence_type: str
    title: str
    summary: str
    year: int | None = None
    partners: list[str]
    outcomes: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MatchResultV2Out(BaseModel):
    id: int
    profile_id: int
    topic_id: int
    eligibility_fit: float
    thematic_fit: float
    impact_fit: float
    implementation_fit: float
    consortium_fit: float
    data_ai_fit: float
    evidence_strength: float
    overall_fit: float
    gap_score: float
    readiness_score: float
    partner_dependency_score: float
    submission_priority: float
    confidence: float
    recommendation: str
    recommended_role: str
    model_version: str
    generated_at: datetime

    class Config:
        from_attributes = True


class MatchExplanationV2Out(BaseModel):
    match_result_id: int
    supporting_topic_sections: list[dict[str, Any]] = Field(default_factory=list)
    supporting_profile_sections: list[dict[str, Any]] = Field(default_factory=list)
    must_have_gaps: list[str] = Field(default_factory=list)
    nice_to_have_gaps: list[str] = Field(default_factory=list)
    suggested_partner_types: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    why_fit: list[str] = Field(default_factory=list)
    why_not_fit: list[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class TopicDecisionCardV2Out(BaseModel):
    profile_id: int
    topic_id: int
    topic_code: str
    title: str
    recommendation: str
    recommended_role: str
    overall_fit: float
    gap_score: float
    readiness_score: float
    partner_dependency_score: float
    submission_priority: float
    confidence: float
    dimensions: dict[str, float]
    why_fit: list[str]
    why_not_fit: list[str]
    must_have_gaps: list[str]
    nice_to_have_gaps: list[str]
    suggested_partner_types: list[str]
    suggested_actions: list[str]
