from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select, literal
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.db.session import get_db
from app.models.company_profile import CompanyProfile
from app.models.draft_document import DraftDocument
from app.models.monthly_report import MonthlyReport
from app.models.opportunity_workflow import OpportunityWorkflow
from app.models.match_result_v2 import MatchResultV2
from app.models.profile_capability import ProfileCapability
from app.models.profile_evidence import ProfileEvidence
from app.models.topic import Topic
from app.models.topic_match import TopicMatch
from app.schemas.api import (
    ProfileCreate,
    ProfileOut,
    ProfileUpdate,
    TopicOut,
    TopicDetailOut,
    MatchOut,
    ReportOut,
    DraftOut,
    TopicFitOut,
    ReportDraftItemOut,
    BrokerageEventOut,
    DeadlineAlertOut,
    ReportAssistantQueryIn,
    ReportAssistantOut,
    FitAssistantQueryIn,
    FitAssistantOut,
    WorkProgrammeTextIn,
    DashboardOverviewOut,
    DecisionReportOut,
    OpportunityWorkflowUpsertIn,
    OpportunityWorkflowOut,
    MatchRecomputeV2In,
    MatchRecomputeV2Out,
    ProfileCapabilityIn,
    ProfileCapabilityOut,
    ProfileEvidenceIn,
    ProfileEvidenceOut,
    MatchResultV2Out,
    MatchExplanationV2Out,
    TopicDecisionCardV2Out,
)
from app.services.report_assistant_service import answer_report_query
from app.services.fit_assistant_service import answer_fit_query
from app.services.draft_hunter_service import run_draft_hunter
from app.services.ingestion_service import ingest_calls
from app.services.matching_service import recompute_matches
from app.services.embedding_service import EmbeddingService
from app.services.matching_v2_service import (
    build_topic_decision_card_v2,
    ensure_v2_schema,
    GroqRateLimitError,
    get_match_explanation_v2,
    list_matches_v2,
    recompute_matches_v2,
)
from app.services.dashboard_service import compute_dashboard_overview, generate_decision_report
from app.services.dashboard_v2_service import compute_dashboard_overview_v2, generate_decision_report_v2
from app.services.report_service import (
    collect_brokerage_report_items,
    collect_deadline_alert_items,
    collect_draft_report_items,
    generate_monthly_report,
    generate_web_report,
)
from app.services.extraction_service import extract_topics_from_pdf
from app.services.file_extract_service import extract_text_from_upload
from app.services.work_programme_pdf_service import ingest_work_programme_pdf, ingest_work_programme_text

router = APIRouter()


@router.get('/health')
def health():
    return {'status': 'ok'}


@router.get('/dashboard/overview', response_model=DashboardOverviewOut)
def dashboard_overview(
    limit: int = Query(default=12, ge=1, le=40),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return compute_dashboard_overview(db=db, user_id=current_user_id, limit=limit)


@router.get('/v2/dashboard/overview', response_model=DashboardOverviewOut)
def dashboard_overview_v2(
    limit: int = Query(default=12, ge=1, le=40),
    model_version: str = Query(default='v2-sprint1'),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return compute_dashboard_overview_v2(db=db, user_id=current_user_id, limit=limit, model_version=model_version)


@router.get('/dashboard/decision-report', response_model=DecisionReportOut)
def dashboard_decision_report(
    limit: int = Query(default=12, ge=1, le=40),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return generate_decision_report(db=db, user_id=current_user_id, limit=limit)


@router.get('/v2/dashboard/decision-report', response_model=DecisionReportOut)
def dashboard_decision_report_v2(
    limit: int = Query(default=12, ge=1, le=40),
    model_version: str = Query(default='v2-sprint1'),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return generate_decision_report_v2(db=db, user_id=current_user_id, limit=limit, model_version=model_version)


@router.get('/workflows', response_model=list[OpportunityWorkflowOut])
def list_workflows(
    profile_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    q = select(OpportunityWorkflow).where(OpportunityWorkflow.user_id == current_user_id)
    if profile_id is not None:
        q = q.where(OpportunityWorkflow.profile_id == profile_id)
    return db.scalars(q.order_by(OpportunityWorkflow.updated_at.desc())).all()


@router.patch('/workflows', response_model=OpportunityWorkflowOut)
def upsert_workflow(
    payload: OpportunityWorkflowUpsertIn,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    profile = db.get(CompanyProfile, payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    topic = db.get(Topic, payload.topic_db_id)
    if not topic:
        raise HTTPException(status_code=404, detail='Topic not found')

    valid_stages = {'Scouting', 'Valutazione', 'Draft', 'Submitted'}
    if payload.stage not in valid_stages:
        raise HTTPException(status_code=400, detail='Invalid stage')

    existing = db.scalars(
        select(OpportunityWorkflow).where(
            OpportunityWorkflow.user_id == current_user_id,
            OpportunityWorkflow.profile_id == payload.profile_id,
            OpportunityWorkflow.topic_id == payload.topic_db_id,
        )
    ).first()

    if existing:
        existing.stage = payload.stage
        existing.priority = payload.priority
        existing.owner = payload.owner
        existing.notes = payload.notes
        db.commit()
        db.refresh(existing)
        return existing

    created = OpportunityWorkflow(
        user_id=current_user_id,
        profile_id=payload.profile_id,
        topic_id=payload.topic_db_id,
        stage=payload.stage,
        priority=payload.priority,
        owner=payload.owner,
        notes=payload.notes,
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


@router.post('/extract-text')
async def extract_text(file: UploadFile = File(...)):
    data = await file.read()
    text, extracted_by = extract_text_from_upload(file.filename or '', file.content_type, data)
    text = text[:300000]
    return {
        'filename': file.filename,
        'content_type': file.content_type,
        'extracted_by': extracted_by,
        'chars': len(text),
        'text': text,
    }


@router.post('/ingest')
def trigger_ingest(db: Session = Depends(get_db)):
    return ingest_calls(db)


@router.post('/ingest/work-programme-pdf')
async def trigger_ingest_work_programme_pdf(
    file: UploadFile = File(...),
    cluster: str | None = Query(default='CL1'),
    profile_id: int | None = Query(default=None),
    auto_match: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    data = await file.read()
    result = ingest_work_programme_pdf(
        db=db,
        filename=file.filename or 'work-programme.pdf',
        content_type=file.content_type,
        data=data,
        cluster_hint=cluster,
    )

    matched_profiles = 0
    if profile_id is not None:
        p = db.get(CompanyProfile, profile_id)
        if not p:
            raise HTTPException(status_code=404, detail='Profile not found')
        if p.user_id != current_user_id:
            raise HTTPException(status_code=403, detail='Forbidden profile')
        recompute_matches(db, profile_id)
        matched_profiles = 1
    elif auto_match:
        profiles = db.scalars(select(CompanyProfile).where(CompanyProfile.user_id == current_user_id)).all()
        for p in profiles:
            recompute_matches(db, p.id)
        matched_profiles = len(profiles)

    result['matched_profiles'] = matched_profiles
    return result


@router.post('/ingest/work-programme-text')
def trigger_ingest_work_programme_text(
    payload: WorkProgrammeTextIn,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    result = ingest_work_programme_text(
        db=db,
        text=payload.text,
        cluster_hint=payload.cluster,
    )

    matched_profiles = 0
    if payload.profile_id is not None:
        p = db.get(CompanyProfile, payload.profile_id)
        if not p:
            raise HTTPException(status_code=404, detail='Profile not found')
        if p.user_id != current_user_id:
            raise HTTPException(status_code=403, detail='Forbidden profile')
        recompute_matches(db, payload.profile_id)
        matched_profiles = 1
    elif payload.auto_match:
        profiles = db.scalars(select(CompanyProfile).where(CompanyProfile.user_id == current_user_id)).all()
        for p in profiles:
            recompute_matches(db, p.id)
        matched_profiles = len(profiles)

    result['matched_profiles'] = matched_profiles
    return result


@router.post('/ingest/extract-topics')
async def extract_topics_endpoint(
    file: UploadFile = File(...),
):
    """Extract structured topics from an EU Work Programme PDF using Groq LLM."""
    data = await file.read()
    result = extract_topics_from_pdf(data=data, filename=file.filename or 'upload.pdf')
    return result


@router.post('/draft-hunter')
def trigger_draft_hunter(db: Session = Depends(get_db)):
    return run_draft_hunter(db)


@router.post('/reports/monthly', response_model=ReportOut)
def trigger_report(
    month: str | None = None,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return generate_monthly_report(db, month=month, user_id=current_user_id)


@router.post('/reports/drafts/run', response_model=ReportOut)
def trigger_draft_report(
    month: str | None = None,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return generate_web_report(db, report_kind='drafts', month=month, user_id=current_user_id)


@router.get('/reports/drafts/items', response_model=list[ReportDraftItemOut])
def list_draft_report_items(current_user_id: str = Depends(get_current_user_id)):
    _ = current_user_id
    return collect_draft_report_items()


@router.post('/reports/brokerage/run', response_model=ReportOut)
def trigger_brokerage_report(
    month: str | None = None,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return generate_web_report(db, report_kind='brokerage', month=month, user_id=current_user_id)


@router.get('/reports/brokerage/items', response_model=list[BrokerageEventOut])
def list_brokerage_report_items(current_user_id: str = Depends(get_current_user_id)):
    _ = current_user_id
    return collect_brokerage_report_items()


@router.post('/reports/alerts/run', response_model=ReportOut)
def trigger_alert_report(
    month: str | None = None,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    return generate_web_report(db, report_kind='alerts', month=month, user_id=current_user_id)


@router.get('/reports/alerts/items', response_model=list[DeadlineAlertOut])
def list_alert_report_items(current_user_id: str = Depends(get_current_user_id)):
    _ = current_user_id
    return collect_deadline_alert_items()


@router.post('/reports/assistant/query', response_model=ReportAssistantOut)
def report_assistant_query(
    payload: ReportAssistantQueryIn,
    current_user_id: str = Depends(get_current_user_id),
):
    _ = current_user_id
    result = answer_report_query(payload.query)
    return {'answer': result.answer, 'sources': result.sources}


@router.post('/fit/assistant/query', response_model=FitAssistantOut)
def fit_assistant_query(
    payload: FitAssistantQueryIn,
    current_user_id: str = Depends(get_current_user_id),
):
    _ = current_user_id
    result = answer_fit_query(payload.model_dump())
    return {'answer': result.answer, 'mode': result.mode, 'cached': result.cached, 'sources': result.sources}


@router.get('/reports/monthly', response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    return db.scalars(
        select(MonthlyReport)
        .where(MonthlyReport.user_id == current_user_id)
        .order_by(MonthlyReport.created_at.desc())
    ).all()


@router.get('/drafts', response_model=list[DraftOut])
def list_drafts(db: Session = Depends(get_db), current_user_id: str = Depends(get_current_user_id)):
    _ = current_user_id
    return db.scalars(select(DraftDocument).order_by(DraftDocument.discovered_at.desc())).all()


@router.post('/profiles', response_model=ProfileOut)
def create_profile(
    payload: ProfileCreate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    data = payload.model_dump()
    data['user_id'] = current_user_id
    p = CompanyProfile(**data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get('/profiles', response_model=list[ProfileOut])
def list_profiles(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    target_user = user_id or current_user_id
    if target_user != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden user scope')
    q = select(CompanyProfile).where(CompanyProfile.user_id == target_user)
    return db.scalars(q.order_by(CompanyProfile.updated_at.desc())).all()


@router.patch('/profiles/{profile_id}', response_model=ProfileOut)
def update_profile(
    profile_id: int,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    p = db.get(CompanyProfile, profile_id)
    if not p:
        raise HTTPException(status_code=404, detail='Profile not found')
    if p.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.post('/profiles/{profile_id}/match')
def match_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    p = db.get(CompanyProfile, profile_id)
    if not p:
        raise HTTPException(status_code=404, detail='Profile not found')
    if p.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')
    return recompute_matches(db, profile_id)


@router.post('/v2/matches/recompute', response_model=MatchRecomputeV2Out)
def recompute_matches_v2_route(
    payload: MatchRecomputeV2In,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    profile = db.get(CompanyProfile, payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    try:
        return recompute_matches_v2(
            db=db,
            profile_id=payload.profile_id,
            model_version=payload.model_version,
            limit_topics=payload.limit_topics,
        )
    except GroqRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post('/v2/profiles/{profile_id}/capabilities', response_model=ProfileCapabilityOut)
def create_profile_capability(
    profile_id: int,
    payload: ProfileCapabilityIn,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    embedder = EmbeddingService()
    row = ProfileCapability(
        profile_id=profile_id,
        name=payload.name,
        description=payload.description,
        domain_tags=payload.domain_tags,
        maturity_level=payload.maturity_level,
        keywords=payload.keywords,
        embedding=embedder.embed(f'{payload.name}\n{payload.description}\n{", ".join(payload.keywords)}'),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get('/v2/profiles/{profile_id}/capabilities', response_model=list[ProfileCapabilityOut])
def list_profile_capabilities(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')
    return db.scalars(
        select(ProfileCapability)
        .where(ProfileCapability.profile_id == profile_id)
        .order_by(ProfileCapability.updated_at.desc())
    ).all()


@router.post('/v2/profiles/{profile_id}/evidence', response_model=ProfileEvidenceOut)
def create_profile_evidence(
    profile_id: int,
    payload: ProfileEvidenceIn,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    embedder = EmbeddingService()
    row = ProfileEvidence(
        profile_id=profile_id,
        evidence_type=payload.evidence_type,
        title=payload.title,
        summary=payload.summary,
        year=payload.year,
        partners=payload.partners,
        outcomes=payload.outcomes,
        embedding=embedder.embed(f'{payload.evidence_type}\n{payload.title}\n{payload.summary}\n{payload.outcomes or ""}'),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get('/v2/profiles/{profile_id}/evidence', response_model=list[ProfileEvidenceOut])
def list_profile_evidence(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')
    return db.scalars(
        select(ProfileEvidence)
        .where(ProfileEvidence.profile_id == profile_id)
        .order_by(ProfileEvidence.updated_at.desc())
    ).all()


@router.get('/v2/profiles/{profile_id}/matches', response_model=list[MatchResultV2Out])
def get_profile_matches_v2(
    profile_id: int,
    model_version: str = Query(default='v2-sprint1'),
    min_overall_fit: float | None = Query(default=None, ge=0, le=100),
    recommendation: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')
    return list_matches_v2(
        db=db,
        profile_id=profile_id,
        model_version=model_version,
        min_overall_fit=min_overall_fit,
        recommendation=recommendation,
        limit=limit,
    )


@router.get('/v2/matches/{match_result_id}/explanation', response_model=MatchExplanationV2Out)
def get_match_explanation_route_v2(
    match_result_id: int,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    row = get_match_explanation_v2(db, match_result_id)
    if not row:
        raise HTTPException(status_code=404, detail='Match explanation not found')

    # Ownership check through match_result -> profile.
    match = db.get(MatchResultV2, match_result_id)
    if not match:
        raise HTTPException(status_code=404, detail='Match result not found')
    profile = db.get(CompanyProfile, match.profile_id)
    if not profile or profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile scope')
    return row


@router.get('/v2/topics/{topic_id}/decision-card', response_model=TopicDecisionCardV2Out)
def get_topic_decision_card_v2(
    topic_id: int,
    profile_id: int = Query(...),
    model_version: str = Query(default='v2-sprint1'),
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    ensure_v2_schema()
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Profile not found')
    if profile.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')
    payload = build_topic_decision_card_v2(
        db=db,
        profile_id=profile_id,
        topic_id=topic_id,
        model_version=model_version,
    )
    if not payload:
        raise HTTPException(status_code=404, detail='Decision card not found, run v2 recompute first')
    return payload


@router.get('/profiles/{profile_id}/matches', response_model=list[MatchOut])
def get_profile_matches(
    profile_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    p = db.get(CompanyProfile, profile_id)
    if not p:
        raise HTTPException(status_code=404, detail='Profile not found')
    if p.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    rows = db.scalars(
        select(TopicMatch)
        .where(TopicMatch.profile_id == profile_id)
        .order_by(TopicMatch.adjusted_score.desc())
        .limit(limit)
    ).all()
    return rows


@router.get('/topics', response_model=list[TopicOut])
def list_topics(
    cluster: str | None = None,
    action_type: str | None = None,
    trl_min: int | None = None,
    trl_max: int | None = None,
    profile_id: int | None = None,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    if profile_id is not None:
        p = db.get(CompanyProfile, profile_id)
        if not p:
            raise HTTPException(status_code=404, detail='Profile not found')
        if p.user_id != current_user_id:
            raise HTTPException(status_code=403, detail='Forbidden profile')

    if profile_id is not None:
        q = select(Topic, TopicMatch.adjusted_score)
        q = q.join(
            TopicMatch,
            (TopicMatch.topic_id == Topic.id) & (TopicMatch.profile_id == profile_id),
            isouter=True,
        )
    else:
        q = select(Topic, literal(None).label('adjusted_score'))

    if cluster:
        q = q.where(Topic.cluster == cluster)
    if action_type:
        q = q.where(Topic.action_type == action_type)
    if trl_min is not None:
        q = q.where(Topic.trl_min >= trl_min)
    if trl_max is not None:
        q = q.where(Topic.trl_max <= trl_max)

    if profile_id is not None:
        q = q.order_by(TopicMatch.adjusted_score.desc().nulls_last(), Topic.deadline.asc().nulls_last())
    else:
        q = q.order_by(Topic.deadline.asc().nulls_last())

    rows = db.execute(q).all()
    payload = []
    for topic, score in rows:
        item = TopicOut.model_validate(topic, from_attributes=True).model_dump()
        item['adjusted_score'] = score
        metadata = topic.metadata_json or {}
        item['procedure_stage'] = metadata.get('procedure_stage')
        flags = metadata.get('compliance_flags') or []
        item['compliance_flags'] = [x for x in flags if isinstance(x, str)]
        payload.append(item)
    return payload


@router.get('/topics/{topic_id}', response_model=TopicDetailOut)
def topic_detail(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    _ = current_user_id
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail='Topic not found')
    return topic


@router.get('/topics/{topic_id}/fit', response_model=TopicFitOut)
def topic_fit(
    topic_id: int,
    profile_id: int,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
):
    p = db.get(CompanyProfile, profile_id)
    if not p:
        raise HTTPException(status_code=404, detail='Profile not found')
    if p.user_id != current_user_id:
        raise HTTPException(status_code=403, detail='Forbidden profile')

    match = db.scalars(
        select(TopicMatch).where(TopicMatch.topic_id == topic_id).where(TopicMatch.profile_id == profile_id)
    ).first()
    if not match:
        raise HTTPException(status_code=404, detail='Match not found, run profile matching first')

    topic = db.get(Topic, topic_id)
    suggestions = []
    text = f"{topic.title} {topic.scope or ''}".lower() if topic else ''
    if 'pilot' in text or 'demonstration' in text:
        suggestions.append('Industrial end-user / pilot site')
    if 'ai' in text or 'digital' in text:
        suggestions.append('AI/data platform provider')
    if 'regulation' in text or 'ethic' in text:
        suggestions.append('Policy/regulatory specialist')
    if not suggestions:
        suggestions = ['Research organization', 'Industrial partner']

    return TopicFitOut(
        topic_id=topic_id,
        profile_id=profile_id,
        adjusted_score=match.adjusted_score,
        recommendation=match.recommendation,
        gaps=match.gaps,
        evidence_snippets=match.evidence_snippets,
        suggested_partner_types=suggestions,
    )
