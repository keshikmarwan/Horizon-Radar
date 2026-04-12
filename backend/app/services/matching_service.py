from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.company_profile import CompanyProfile
from app.models.topic import Topic
from app.models.topic_match import TopicMatch
from app.services.embedding_service import EmbeddingService


def _rule_adjustment(profile: CompanyProfile, topic: Topic, base: float) -> tuple[float, list[str], str, str]:
    constraints = profile.constraints or {}
    score = base
    evidence = []

    target_trl = constraints.get('preferred_trl')
    if target_trl is not None and topic.trl_min is not None:
        if topic.trl_min <= target_trl <= (topic.trl_max or topic.trl_min):
            score += 0.08
            evidence.append(f'TRL aligns with preferred range around TRL {target_trl}.')
        else:
            score -= 0.06

    must_keywords = constraints.get('must_have_keywords', [])
    haystack = f"{topic.title} {topic.expected_outcomes or ''} {topic.scope or ''}".lower()
    missing = [k for k in must_keywords if k.lower() not in haystack]
    if missing:
        score -= min(0.2, 0.05 * len(missing))
    else:
        score += 0.05 if must_keywords else 0.0

    avoid_actions = constraints.get('avoid_action_types', [])
    if topic.action_type and topic.action_type in avoid_actions:
        score -= 0.1

    gaps = 'Missing keywords: ' + ', '.join(missing) if missing else 'No critical gaps detected.'
    if score >= 0.65:
        rec = 'GO: strong fit with current profile.'
    elif score >= 0.45:
        rec = 'WATCH: potential fit, requires partner and scope refinement.'
    else:
        rec = 'NO-GO: weak fit against profile and constraints.'

    if not evidence:
        evidence = [topic.title[:180], (topic.expected_outcomes or '')[:180]]

    return max(min(score, 1.0), -1.0), evidence[:3], rec, gaps


def recompute_matches(db: Session, profile_id: int) -> dict:
    profile = db.get(CompanyProfile, profile_id)
    if not profile:
        raise ValueError('Profile not found')

    embedder = EmbeddingService()
    profile_embedding = embedder.embed(f"{profile.description}\nTags: {', '.join(profile.tags)}")
    topics = db.scalars(select(Topic)).all()

    db.execute(delete(TopicMatch).where(TopicMatch.profile_id == profile_id))

    inserted = 0
    for topic in topics:
        if not topic.embedding:
            continue
        semantic = (embedder.cosine(profile_embedding, topic.embedding) + 1) / 2
        adjusted, evidence, rec, gaps = _rule_adjustment(profile, topic, semantic)

        db.add(TopicMatch(
            profile_id=profile_id,
            topic_id=topic.id,
            semantic_score=float(semantic),
            adjusted_score=float(adjusted),
            recommendation=rec,
            gaps=gaps,
            evidence_snippets=evidence,
        ))
        inserted += 1

    db.commit()
    return {'profile_id': profile_id, 'matches': inserted}
