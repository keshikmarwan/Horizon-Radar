from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import engine
from app.models.company_profile import CompanyProfile
from app.models.match_explanation_v2 import MatchExplanationV2
from app.models.match_result_v2 import MatchResultV2
from app.models.profile_capability import ProfileCapability
from app.models.profile_evidence import ProfileEvidence
from app.models.topic import Topic
from app.models.topic_section import TopicSection
from app.services.embedding_service import EmbeddingService


@dataclass
class _HardFilterResult:
    passed: bool
    reasons: list[str]


def _clamp_0_100(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))


def _normalized_scalar(value: float) -> float:
    return max(0.0, min(1.0, value))


def ensure_v2_schema() -> None:
    # Lightweight bootstrap for environments using create_all without migrations.
    for table in (
        TopicSection.__table__,
        ProfileCapability.__table__,
        ProfileEvidence.__table__,
        MatchResultV2.__table__,
        MatchExplanationV2.__table__,
    ):
        table.create(bind=engine, checkfirst=True)


def _build_profile_text(profile: CompanyProfile, capabilities: list[ProfileCapability], evidence: list[ProfileEvidence]) -> str:
    parts = [profile.name, profile.description, f"Tags: {', '.join(profile.tags or [])}"]
    if capabilities:
        parts.append('Capabilities:')
        for c in capabilities:
            parts.append(f"- {c.name}: {c.description}")
    if evidence:
        parts.append('Evidence:')
        for e in evidence:
            parts.append(f"- {e.title}: {e.summary}")
    return '\n'.join(parts)


def _ensure_topic_sections(db: Session, topics: list[Topic], embedder: EmbeddingService) -> None:
    existing_rows = db.scalars(select(TopicSection.topic_id)).all()
    existing_topic_ids = set(existing_rows)
    buffered: list[TopicSection] = []

    for topic in topics:
        if topic.id in existing_topic_ids:
            continue
        sections: list[tuple[str, str]] = []
        if topic.expected_outcomes:
            sections.append(('expected_outcome', topic.expected_outcomes))
        if topic.scope:
            sections.append(('scope', topic.scope))
        summary_bits = [topic.title]
        if topic.action_type:
            summary_bits.append(f'Action type: {topic.action_type}')
        if topic.cluster:
            summary_bits.append(f'Cluster: {topic.cluster}')
        summary_text = '\n'.join(summary_bits).strip()
        if summary_text:
            sections.append(('call_overview', summary_text))

        for section_type, text in sections:
            cleaned = (text or '').strip()
            if not cleaned:
                continue
            buffered.append(
                TopicSection(
                    topic_id=topic.id,
                    section_type=section_type,
                    text=cleaned,
                    embedding=embedder.embed(cleaned),
                )
            )

    if buffered:
        db.add_all(buffered)
        db.flush()


def _passes_hard_filters(profile: CompanyProfile, topic: Topic) -> _HardFilterResult:
    constraints = profile.constraints or {}
    reasons: list[str] = []

    preferred_clusters = {str(x).strip().upper() for x in (constraints.get('preferred_clusters') or []) if str(x).strip()}
    if preferred_clusters and (topic.cluster or '').upper() not in preferred_clusters:
        reasons.append('Cluster outside preferred scope.')

    preferred_actions = {str(x).strip().upper() for x in (constraints.get('preferred_actions') or []) if str(x).strip()}
    if preferred_actions and (topic.action_type or '').upper() not in preferred_actions:
        reasons.append('Action type not compatible with preferred actions.')

    target_trl = constraints.get('preferred_trl')
    if target_trl is not None and topic.trl_min is not None:
        tmin = topic.trl_min
        tmax = topic.trl_max or topic.trl_min
        if not (tmin <= int(target_trl) <= tmax):
            reasons.append('TRL outside preferred range.')

    max_budget = constraints.get('max_budget_total')
    if max_budget is not None and topic.budget_total is not None and float(topic.budget_total) > float(max_budget):
        reasons.append('Topic budget exceeds max budget threshold.')

    min_budget = constraints.get('min_budget_total')
    if min_budget is not None and topic.budget_total is not None and float(topic.budget_total) < float(min_budget):
        reasons.append('Topic budget below min budget threshold.')

    metadata = topic.metadata_json or {}
    procedure_stage = (metadata.get('procedure_stage') or '').strip().lower()
    stage_required = (constraints.get('required_stage_type') or '').strip().lower()
    if stage_required in {'single-stage', 'two-stage'} and procedure_stage and procedure_stage != stage_required:
        reasons.append('Stage type is not compatible with profile constraints.')

    required_flags = {str(x).strip().lower() for x in (constraints.get('required_compliance_flags') or []) if str(x).strip()}
    topic_flags = {str(x).strip().lower() for x in (metadata.get('compliance_flags') or []) if str(x).strip()}
    if required_flags and not required_flags.issubset(topic_flags):
        reasons.append('Required compliance flags are missing.')

    forbidden_flags = {str(x).strip().lower() for x in (constraints.get('forbidden_compliance_flags') or []) if str(x).strip()}
    if forbidden_flags.intersection(topic_flags):
        reasons.append('Topic includes forbidden compliance flags.')

    return _HardFilterResult(passed=len(reasons) == 0, reasons=reasons)


def _semantic_components(
    embedder: EmbeddingService,
    profile_vec: list[float],
    topic: Topic,
    topic_sections: list[TopicSection],
) -> tuple[float, list[dict]]:
    base_semantic = 0.0
    evidence_sections: list[dict] = []
    if topic.embedding:
        base_semantic = (embedder.cosine(profile_vec, topic.embedding) + 1.0) / 2.0

    best_section_score = 0.0
    for section in topic_sections:
        if not section.embedding:
            continue
        section_score = (embedder.cosine(profile_vec, section.embedding) + 1.0) / 2.0
        if section_score > best_section_score:
            best_section_score = section_score
        if section_score >= 0.55:
            evidence_sections.append(
                {
                    'section_type': section.section_type,
                    'score': round(section_score * 100, 2),
                    'text': section.text[:300],
                }
            )
    merged = (base_semantic * 0.6) + (best_section_score * 0.4)
    return _normalized_scalar(merged), evidence_sections[:6]


def recompute_matches_v2(
    db: Session,
    profile_id: int,
    model_version: str = 'v2-sprint1',
    limit_topics: int | None = None,
) -> dict:
    ensure_v2_schema()

    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise ValueError('Profile not found')

    embedder = EmbeddingService()
    capabilities = db.scalars(select(ProfileCapability).where(ProfileCapability.profile_id == profile_id)).all()
    evidence_rows = db.scalars(select(ProfileEvidence).where(ProfileEvidence.profile_id == profile_id)).all()
    profile_text = _build_profile_text(profile, capabilities, evidence_rows)
    profile_vec = embedder.embed(profile_text)

    topics_query = select(Topic).order_by(Topic.deadline.asc().nulls_last())
    if limit_topics is not None:
        topics_query = topics_query.limit(limit_topics)
    topics = db.scalars(topics_query).all()

    _ensure_topic_sections(db, topics, embedder)

    section_rows = db.scalars(select(TopicSection)).all()
    sections_by_topic: dict[int, list[TopicSection]] = {}
    for row in section_rows:
        sections_by_topic.setdefault(row.topic_id, []).append(row)

    previous_rows = db.scalars(
        select(MatchResultV2).where(
            MatchResultV2.profile_id == profile_id,
            MatchResultV2.model_version == model_version,
        )
    ).all()
    previous_ids = [r.id for r in previous_rows]
    if previous_ids:
        db.execute(delete(MatchExplanationV2).where(MatchExplanationV2.match_result_id.in_(previous_ids)))
    db.execute(
        delete(MatchResultV2).where(
            MatchResultV2.profile_id == profile_id,
            MatchResultV2.model_version == model_version,
        )
    )

    skipped = 0
    evaluated: list[dict[str, Any]] = []

    for topic in topics:
        hard_filter = _passes_hard_filters(profile, topic)
        if not hard_filter.passed:
            skipped += 1
            continue

        semantic_score, supporting_sections = _semantic_components(
            embedder=embedder,
            profile_vec=profile_vec,
            topic=topic,
            topic_sections=sections_by_topic.get(topic.id, []),
        )

        eligibility_fit = _clamp_0_100(65 + (semantic_score * 25))
        thematic_fit = _clamp_0_100(semantic_score * 100)
        impact_fit = _clamp_0_100(35 + thematic_fit * 0.5)
        implementation_fit = _clamp_0_100(40 + thematic_fit * 0.45)
        consortium_fit = _clamp_0_100(45 + thematic_fit * 0.4)
        data_ai_fit = _clamp_0_100(30 + thematic_fit * 0.55)
        evidence_strength = _clamp_0_100(35 + (len(supporting_sections) * 8))

        overall_fit = _clamp_0_100(
            (0.20 * eligibility_fit)
            + (0.24 * thematic_fit)
            + (0.16 * impact_fit)
            + (0.14 * implementation_fit)
            + (0.14 * consortium_fit)
            + (0.12 * evidence_strength)
        )

        must_have_gaps: list[str] = []
        if overall_fit < 55:
            must_have_gaps.append('Low thematic alignment against current profile.')
        if evidence_strength < 55:
            must_have_gaps.append('Limited evidence coverage for expected outcomes/scope.')

        nice_to_have_gaps: list[str] = []
        if consortium_fit < 60:
            nice_to_have_gaps.append('Consortium role clarity should be improved.')
        if data_ai_fit < 60:
            nice_to_have_gaps.append('Data contribution should be strengthened.')

        gap_score = _clamp_0_100((len(must_have_gaps) * 35) + (len(nice_to_have_gaps) * 12))
        readiness_score = _clamp_0_100(max(0, overall_fit - (0.5 * gap_score)))
        partner_dependency_score = _clamp_0_100(100 - consortium_fit)

        deadline_urgency = 0.0
        if topic.deadline:
            deadline = topic.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            days_left = max(0, (deadline.date() - datetime.now(timezone.utc).date()).days)
            deadline_urgency = 100.0 if days_left <= 15 else 70.0 if days_left <= 45 else 45.0

        submission_priority = _clamp_0_100((0.55 * overall_fit) + (0.25 * readiness_score) + (0.20 * deadline_urgency))
        confidence = _clamp_0_100((0.7 * thematic_fit) + (0.3 * evidence_strength))

        if overall_fit >= 72 and gap_score <= 35:
            recommendation = 'go'
            recommended_role = 'partner'
        elif overall_fit >= 50:
            recommendation = 'watch'
            recommended_role = 'watch_only'
        else:
            recommendation = 'no_go'
            recommended_role = 'watch_only'

        evaluated.append(
            {
                'topic': topic,
                'eligibility_fit': eligibility_fit,
                'thematic_fit': thematic_fit,
                'impact_fit': impact_fit,
                'implementation_fit': implementation_fit,
                'consortium_fit': consortium_fit,
                'data_ai_fit': data_ai_fit,
                'evidence_strength': evidence_strength,
                'overall_fit': overall_fit,
                'gap_score': gap_score,
                'readiness_score': readiness_score,
                'partner_dependency_score': partner_dependency_score,
                'submission_priority': submission_priority,
                'confidence': confidence,
                'recommendation': recommendation,
                'recommended_role': recommended_role,
                'supporting_sections': supporting_sections,
                'must_have_gaps': must_have_gaps,
                'nice_to_have_gaps': nice_to_have_gaps,
                'why_fit': [
                    f'Thematic fit score: {thematic_fit:.1f}/100',
                    f'Eligibility fit score: {eligibility_fit:.1f}/100',
                ],
                'why_not_fit': [*must_have_gaps, *nice_to_have_gaps],
                'suggested_partner_types': [
                    'Research organization',
                    'Clinical/validation partner',
                ],
                'suggested_actions': [
                    'Validate eligibility constraints with call manager.',
                    'Refine consortium role and technical contribution statement.',
                ],
            }
        )

    inserted = 0
    results: list[MatchResultV2] = []
    for item in evaluated:
        topic: Topic = item['topic']
        result_row = MatchResultV2(
            profile_id=profile_id,
            topic_id=topic.id,
            eligibility_fit=item['eligibility_fit'],
            thematic_fit=item['thematic_fit'],
            impact_fit=item['impact_fit'],
            implementation_fit=item['implementation_fit'],
            consortium_fit=item['consortium_fit'],
            data_ai_fit=item['data_ai_fit'],
            evidence_strength=item['evidence_strength'],
            overall_fit=item['overall_fit'],
            gap_score=item['gap_score'],
            readiness_score=item['readiness_score'],
            partner_dependency_score=item['partner_dependency_score'],
            submission_priority=item['submission_priority'],
            confidence=item['confidence'],
            recommendation=item['recommendation'],
            recommended_role=item['recommended_role'],
            model_version=model_version,
        )
        db.add(result_row)
        db.flush()

        explanation = MatchExplanationV2(
            match_result_id=result_row.id,
            supporting_topic_sections=item['supporting_sections'],
            supporting_profile_sections=[
                {'type': 'profile_description', 'text': profile.description[:350]},
            ],
            must_have_gaps=item['must_have_gaps'],
            nice_to_have_gaps=item['nice_to_have_gaps'],
            suggested_partner_types=item['suggested_partner_types'],
            suggested_actions=item['suggested_actions'],
            why_fit=item['why_fit'],
            why_not_fit=item['why_not_fit'],
        )
        db.add(explanation)
        inserted += 1
        results.append(result_row)

    db.commit()

    top_results = sorted(results, key=lambda x: x.submission_priority, reverse=True)[:10]
    return {
        'profile_id': profile_id,
        'model_version': model_version,
        'evaluated_topics': len(topics),
        'matches_inserted': inserted,
        'matches_skipped_by_hard_filters': skipped,
        'top_topics': [
            {
                'topic_db_id': r.topic_id,
                'submission_priority': r.submission_priority,
                'overall_fit': r.overall_fit,
                'recommendation': r.recommendation,
            }
            for r in top_results
        ],
    }


def list_matches_v2(
    db: Session,
    profile_id: int,
    model_version: str = 'v2-sprint1',
    min_overall_fit: float | None = None,
    recommendation: str | None = None,
    limit: int = 100,
) -> list[MatchResultV2]:
    ensure_v2_schema()
    q = select(MatchResultV2).where(
        MatchResultV2.profile_id == profile_id,
        MatchResultV2.model_version == model_version,
    )
    if min_overall_fit is not None:
        q = q.where(MatchResultV2.overall_fit >= min_overall_fit)
    if recommendation:
        q = q.where(MatchResultV2.recommendation == recommendation.lower().strip())
    q = q.order_by(MatchResultV2.submission_priority.desc(), MatchResultV2.overall_fit.desc()).limit(limit)
    return db.scalars(q).all()


def get_match_explanation_v2(db: Session, match_result_id: int) -> MatchExplanationV2 | None:
    ensure_v2_schema()
    return db.scalars(select(MatchExplanationV2).where(MatchExplanationV2.match_result_id == match_result_id)).first()


def build_topic_decision_card_v2(
    db: Session,
    profile_id: int,
    topic_id: int,
    model_version: str = 'v2-sprint1',
) -> dict | None:
    ensure_v2_schema()
    match = db.scalars(
        select(MatchResultV2).where(
            MatchResultV2.profile_id == profile_id,
            MatchResultV2.topic_id == topic_id,
            MatchResultV2.model_version == model_version,
        )
    ).first()
    if not match:
        return None

    topic = db.get(Topic, topic_id)
    if not topic:
        return None

    explanation = get_match_explanation_v2(db, match.id)
    return {
        'profile_id': profile_id,
        'topic_id': topic_id,
        'topic_code': topic.topic_id,
        'title': topic.title,
        'recommendation': match.recommendation,
        'recommended_role': match.recommended_role,
        'overall_fit': match.overall_fit,
        'gap_score': match.gap_score,
        'readiness_score': match.readiness_score,
        'partner_dependency_score': match.partner_dependency_score,
        'submission_priority': match.submission_priority,
        'confidence': match.confidence,
        'dimensions': {
            'eligibility_fit': match.eligibility_fit,
            'thematic_fit': match.thematic_fit,
            'impact_fit': match.impact_fit,
            'implementation_fit': match.implementation_fit,
            'consortium_fit': match.consortium_fit,
            'data_ai_fit': match.data_ai_fit,
            'evidence_strength': match.evidence_strength,
        },
        'why_fit': explanation.why_fit if explanation else [],
        'why_not_fit': explanation.why_not_fit if explanation else [],
        'must_have_gaps': explanation.must_have_gaps if explanation else [],
        'nice_to_have_gaps': explanation.nice_to_have_gaps if explanation else [],
        'suggested_partner_types': explanation.suggested_partner_types if explanation else [],
        'suggested_actions': explanation.suggested_actions if explanation else [],
    }
