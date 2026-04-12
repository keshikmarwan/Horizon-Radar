from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.match_result_v2 import MatchResultV2
from app.models.opportunity_workflow import OpportunityWorkflow
from app.models.topic import Topic


def _derive_stage_from_priority(priority: float) -> str:
    if priority >= 90:
        return 'Submitted'
    if priority >= 78:
        return 'Draft'
    if priority >= 60:
        return 'Valutazione'
    return 'Scouting'


def _format_budget(value: float | None) -> str | None:
    if value is None:
        return None
    if value >= 1_000_000:
        return f'€{(value / 1_000_000):.1f}M'
    if value >= 1_000:
        return f'€{(value / 1_000):.0f}K'
    return f'€{round(value)}'


def _trl_label(topic: Topic) -> str | None:
    if topic.trl_min is not None and topic.trl_max is not None:
        return f'{topic.trl_min}-{topic.trl_max}'
    if topic.trl_min is not None:
        return str(topic.trl_min)
    return None


def compute_dashboard_overview_v2(db: Session, user_id: str, limit: int = 12, model_version: str = 'v2-sprint1') -> dict:
    profiles = db.scalars(
        select(CompanyProfile)
        .where(CompanyProfile.user_id == user_id)
        .order_by(CompanyProfile.updated_at.desc())
    ).all()
    if not profiles:
        return {
            'kpis': {
                'active_opportunities': 0,
                'average_fit': 0,
                'nearest_deadline_days': None,
                'critical_risks': 0,
            },
            'pipeline': [{'stage': x, 'count': 0} for x in ['Scouting', 'Valutazione', 'Draft', 'Submitted']],
            'opportunities': [],
            'compliance_risks': [],
            'alerts': [],
            'roadmap': [],
            'generated_at': datetime.now(timezone.utc),
        }

    profile_by_id = {p.id: p for p in profiles}
    rows = db.execute(
        select(MatchResultV2, Topic)
        .join(Topic, Topic.id == MatchResultV2.topic_id)
        .where(
            MatchResultV2.profile_id.in_(profile_by_id.keys()),
            MatchResultV2.model_version == model_version,
        )
        .order_by(MatchResultV2.submission_priority.desc(), MatchResultV2.overall_fit.desc())
    ).all()

    workflows = db.scalars(select(OpportunityWorkflow).where(OpportunityWorkflow.user_id == user_id)).all()
    workflow_by_key = {(w.profile_id, w.topic_id): w for w in workflows}

    stage_counts = {'Scouting': 0, 'Valutazione': 0, 'Draft': 0, 'Submitted': 0}
    opportunities: list[dict] = []
    fit_values: list[int] = []
    active_opportunities = 0
    risk_count = 0
    nearest_deadline_days: int | None = None
    now = datetime.now(timezone.utc)
    compliance_counts: dict[str, int] = {}

    for match, topic in rows:
        score = round(match.overall_fit)
        fit_values.append(score)
        workflow = workflow_by_key.get((match.profile_id, topic.id))
        stage = workflow.stage if workflow else _derive_stage_from_priority(match.submission_priority)
        stage_counts[stage] += 1

        if score >= 50:
            active_opportunities += 1
        if score < 55 or match.gap_score >= 55:
            risk_count += 1

        metadata = topic.metadata_json or {}
        flags = [x for x in (metadata.get('compliance_flags') or []) if isinstance(x, str)]
        for flag in flags:
            compliance_counts[flag] = compliance_counts.get(flag, 0) + 1

        if topic.deadline:
            deadline = topic.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            delta_days = max(0, (deadline.date() - now.date()).days)
            if nearest_deadline_days is None or delta_days < nearest_deadline_days:
                nearest_deadline_days = delta_days

        if len(opportunities) < limit:
            profile = profile_by_id.get(match.profile_id)
            opportunities.append(
                {
                    'id': f'{match.profile_id}-{topic.id}',
                    'profile_id': match.profile_id,
                    'topic_db_id': topic.id,
                    'topic_id': topic.topic_id,
                    'title': topic.title,
                    'profile_name': profile.name if profile else f'Profile {match.profile_id}',
                    'cluster': topic.cluster,
                    'fit_score': score,
                    'stage': stage,
                    'trl': _trl_label(topic),
                    'budget': _format_budget(topic.budget_total),
                    'deadline': topic.deadline,
                    'next_action': 'Close must-have gaps and validate submission role.',
                    'procedure_stage': (metadata.get('procedure_stage') if isinstance(metadata, dict) else None),
                    'compliance_flags': flags,
                    'workflow': {
                        'id': workflow.id,
                        'stage': workflow.stage,
                        'priority': workflow.priority,
                        'owner': workflow.owner,
                        'notes': workflow.notes,
                        'updated_at': workflow.updated_at,
                    } if workflow else None,
                }
            )

    avg_fit = round(sum(fit_values) / len(fit_values)) if fit_values else 0

    alerts: list[dict] = []
    for item in opportunities[:8]:
        if item['deadline'] is None:
            continue
        deadline = item['deadline']
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        days_left = max(0, (deadline.date() - now.date()).days)
        if days_left <= 14:
            alerts.append(
                {
                    'level': 'critical' if days_left <= 7 else 'warning',
                    'title': 'Deadline ravvicinata',
                    'detail': f"{item['topic_id']} scade tra {days_left} giorni.",
                    'topic_id': item['topic_id'],
                }
            )

    top_risks = sorted(
        [{'flag': k, 'count': v} for k, v in compliance_counts.items()],
        key=lambda x: x['count'],
        reverse=True,
    )[:8]

    roadmap = []
    if nearest_deadline_days is not None:
        roadmap = [
            {'label': 'Go/No-Go Review', 'days_remaining': max(3, nearest_deadline_days - 12), 'priority': 'high'},
            {'label': 'Partner Alignment', 'days_remaining': max(5, nearest_deadline_days - 7), 'priority': 'high'},
            {'label': 'Submission Readiness', 'days_remaining': nearest_deadline_days, 'priority': 'critical'},
        ]

    return {
        'kpis': {
            'active_opportunities': active_opportunities,
            'average_fit': avg_fit,
            'nearest_deadline_days': nearest_deadline_days,
            'critical_risks': risk_count,
        },
        'pipeline': [{'stage': k, 'count': v} for k, v in stage_counts.items()],
        'opportunities': opportunities,
        'compliance_risks': top_risks,
        'alerts': alerts[:12],
        'roadmap': roadmap,
        'generated_at': datetime.now(timezone.utc),
    }


def generate_decision_report_v2(db: Session, user_id: str, limit: int = 12, model_version: str = 'v2-sprint1') -> dict:
    overview = compute_dashboard_overview_v2(db=db, user_id=user_id, limit=limit, model_version=model_version)
    kpis = overview['kpis']
    top = overview['opportunities'][:5]
    lines: list[str] = []
    lines.append('# Decision Report V2')
    lines.append(f"- Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Active opportunities: {kpis['active_opportunities']}")
    lines.append(f"- Average fit: {kpis['average_fit']}%")
    lines.append(f"- Critical risks: {kpis['critical_risks']}")
    lines.append('')
    lines.append('## Top Opportunities')
    if not top:
        lines.append('- No opportunities available.')
    else:
        for item in top:
            lines.append(f"- {item['topic_id']} | {item['fit_score']}% | {item['stage']} | {item['next_action']}")

    return {
        'markdown': '\n'.join(lines),
        'generated_at': datetime.now(timezone.utc),
    }
