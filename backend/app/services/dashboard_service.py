from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.opportunity_workflow import OpportunityWorkflow
from app.models.topic import Topic
from app.models.topic_match import TopicMatch


def _derive_stage(score: float) -> str:
    if score >= 0.90:
        return 'Submitted'
    if score >= 0.78:
        return 'Draft'
    if score >= 0.62:
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


def compute_dashboard_overview(db: Session, user_id: str, limit: int = 12) -> dict:
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
            'pipeline': [
                {'stage': 'Scouting', 'count': 0},
                {'stage': 'Valutazione', 'count': 0},
                {'stage': 'Draft', 'count': 0},
                {'stage': 'Submitted', 'count': 0},
            ],
            'opportunities': [],
            'compliance_risks': [],
            'alerts': [],
            'roadmap': [],
            'generated_at': datetime.now(timezone.utc),
        }

    profile_by_id = {p.id: p for p in profiles}
    rows = db.execute(
        select(TopicMatch, Topic)
        .join(Topic, Topic.id == TopicMatch.topic_id)
        .where(TopicMatch.profile_id.in_(profile_by_id.keys()))
        .order_by(TopicMatch.adjusted_score.desc())
    ).all()

    decision_set_size = max(80, limit * 20)
    candidate_rows = rows[:decision_set_size]

    workflow_rows = db.scalars(
        select(OpportunityWorkflow).where(OpportunityWorkflow.user_id == user_id)
    ).all()
    workflow_by_key = {(w.profile_id, w.topic_id): w for w in workflow_rows}

    opportunities: list[dict] = []
    stage_counts = {'Scouting': 0, 'Valutazione': 0, 'Draft': 0, 'Submitted': 0}
    compliance_counts: dict[str, int] = {}
    blocking_risk_flags = {'admissibility', 'eligibility', 'ethics', 'regulatory'}

    now = datetime.now(timezone.utc)
    nearest_deadline_days: int | None = None
    active_opportunities = 0
    risk_count = 0
    fit_values: list[int] = []
    two_stage_count = 0

    for match, topic in candidate_rows:
        score = max(0, min(100, round((match.adjusted_score or 0) * 100)))
        workflow = workflow_by_key.get((match.profile_id, topic.id))
        stage = workflow.stage if workflow else _derive_stage(match.adjusted_score or 0)
        stage_counts[stage] += 1
        fit_values.append(score)

        metadata = topic.metadata_json or {}
        flags = [x for x in (metadata.get('compliance_flags') or []) if isinstance(x, str)]
        for flag in flags:
            compliance_counts[flag] = compliance_counts.get(flag, 0) + 1
        if metadata.get('procedure_stage') == 'two-stage':
            two_stage_count += 1

        blocking_flag_found = any(flag in blocking_risk_flags for flag in flags)
        if score < 62 or blocking_flag_found:
            risk_count += 1
        if score >= 45:
            active_opportunities += 1

        if topic.deadline:
            deadline = topic.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            days = max(0, (deadline.date() - now.date()).days)
            if nearest_deadline_days is None or days < nearest_deadline_days:
                nearest_deadline_days = days

        if len(opportunities) < limit:
            profile = profile_by_id.get(match.profile_id)
            next_action = (
                f'Gap da chiudere: {match.gaps}'
                if match.gaps and match.gaps != 'No critical gaps detected.'
                else (match.recommendation or 'Procedere con qualificazione tecnica e partner fit.')
            )
            opportunities.append({
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
                'next_action': next_action,
                'procedure_stage': metadata.get('procedure_stage'),
                'compliance_flags': flags,
                'workflow': {
                    'id': workflow.id,
                    'stage': workflow.stage,
                    'priority': workflow.priority,
                    'owner': workflow.owner,
                    'notes': workflow.notes,
                    'updated_at': workflow.updated_at,
                } if workflow else None,
            })

    avg_fit = round(sum(fit_values) / len(fit_values)) if fit_values else 0

    roadmap: list[dict] = []
    if nearest_deadline_days is not None:
        roadmap = [
            {'label': 'Gate 0 - Go/No-Go', 'days_remaining': max(5, nearest_deadline_days - 12), 'priority': 'high'},
            {'label': 'Partner Alignment', 'days_remaining': max(10, nearest_deadline_days - 7), 'priority': 'high'},
            {'label': 'Technical Narrative Freeze', 'days_remaining': max(14, nearest_deadline_days - 3), 'priority': 'medium'},
            {'label': 'Submission Readiness', 'days_remaining': nearest_deadline_days, 'priority': 'critical'},
        ]
        if two_stage_count > 0:
            roadmap.insert(0, {
                'label': 'Stage 1 Concept Validation',
                'days_remaining': max(7, nearest_deadline_days - 18),
                'priority': 'high',
            })

    top_risks = sorted(
        [{'flag': key, 'count': value} for key, value in compliance_counts.items()],
        key=lambda x: x['count'],
        reverse=True,
    )[:8]

    alerts: list[dict] = []
    for item in opportunities[:8]:
        if item['deadline'] is not None:
            deadline = item['deadline']
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            days_to_deadline = max(0, (deadline.date() - now.date()).days)
            if days_to_deadline <= 14:
                alerts.append({
                    'level': 'critical' if days_to_deadline <= 7 else 'warning',
                    'title': 'Deadline ravvicinata',
                    'detail': f"{item['topic_id']} scade tra {days_to_deadline} giorni.",
                    'topic_id': item['topic_id'],
                })

        if item.get('workflow') and (item['workflow'].get('priority') or '').lower() in {'high', 'critical'}:
            if not (item['workflow'].get('owner') or '').strip():
                alerts.append({
                    'level': 'warning',
                    'title': 'Owner mancante',
                    'detail': f"{item['topic_id']} in priorita alta senza owner assegnato.",
                    'topic_id': item['topic_id'],
                })

        if any(flag in {'eligibility', 'admissibility', 'regulatory', 'ethics'} for flag in item.get('compliance_flags', [])):
            alerts.append({
                'level': 'info',
                'title': 'Verifica compliance richiesta',
                'detail': f"{item['topic_id']} richiede check su requisiti compliance/eligibility.",
                'topic_id': item['topic_id'],
            })

    alerts = alerts[:12]

    return {
        'kpis': {
            'active_opportunities': active_opportunities,
            'average_fit': avg_fit,
            'nearest_deadline_days': nearest_deadline_days,
            'critical_risks': risk_count,
        },
        'pipeline': [
            {'stage': 'Scouting', 'count': stage_counts['Scouting']},
            {'stage': 'Valutazione', 'count': stage_counts['Valutazione']},
            {'stage': 'Draft', 'count': stage_counts['Draft']},
            {'stage': 'Submitted', 'count': stage_counts['Submitted']},
        ],
        'opportunities': opportunities,
        'compliance_risks': top_risks,
        'alerts': alerts,
        'roadmap': roadmap,
        'generated_at': datetime.now(timezone.utc),
    }


def generate_decision_report(db: Session, user_id: str, limit: int = 12) -> dict:
    overview = compute_dashboard_overview(db=db, user_id=user_id, limit=limit)
    kpis = overview['kpis']
    pipeline = overview['pipeline']
    top_opps = overview['opportunities'][:5]
    alerts = overview['alerts'][:6]

    lines: list[str] = []
    lines.append('# Decision Report')
    lines.append('')
    lines.append(f"- Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Active opportunities: {kpis['active_opportunities']}")
    lines.append(f"- Average fit: {kpis['average_fit']}%")
    lines.append(f"- Critical risks: {kpis['critical_risks']}")
    lines.append(
        f"- Nearest deadline: {kpis['nearest_deadline_days']} giorni"
        if kpis['nearest_deadline_days'] is not None
        else '- Nearest deadline: n/d'
    )
    lines.append('')
    lines.append('## Pipeline')
    for row in pipeline:
        lines.append(f"- {row['stage']}: {row['count']}")

    lines.append('')
    lines.append('## Top Opportunities')
    if not top_opps:
        lines.append('- Nessuna opportunita disponibile.')
    for item in top_opps:
        lines.append(
            f"- {item['topic_id']} ({item['stage']}, fit {item['fit_score']}%): {item['next_action']}"
        )

    lines.append('')
    lines.append('## Alerts')
    if not alerts:
        lines.append('- Nessun alert attivo.')
    for alert in alerts:
        lines.append(f"- [{alert['level'].upper()}] {alert['title']}: {alert['detail']}")

    lines.append('')
    lines.append('## Compliance Risks')
    if not overview['compliance_risks']:
        lines.append('- Nessun rischio compliance aggregato.')
    for risk in overview['compliance_risks']:
        lines.append(f"- {risk['flag']}: {risk['count']}")

    return {
        'markdown': '\n'.join(lines),
        'generated_at': datetime.now(timezone.utc),
    }
