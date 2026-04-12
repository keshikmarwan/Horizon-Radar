from sqlalchemy import select
from sqlalchemy.orm import Session
from dateutil import parser as dt_parser

from app.models.fetch_snapshot import FetchSnapshot
from app.models.topic import Topic
from app.services.connectors import build_connectors
from app.services.embedding_service import EmbeddingService


def ingest_calls(db: Session) -> dict:
    embedding = EmbeddingService()
    total_topics = 0
    total_snapshots = 0

    for connector in build_connectors():
        topics, snapshots = connector.fetch_topics()

        for source, source_url, local_path, content_hash in snapshots:
            existing_snap = db.scalars(
                select(FetchSnapshot).where(FetchSnapshot.content_hash == content_hash)
            ).first()
            if not existing_snap:
                db.add(FetchSnapshot(
                    source=source,
                    source_url=source_url,
                    local_path=local_path,
                    content_hash=content_hash,
                    content_type='text/html',
                ))
                total_snapshots += 1

        for t in topics:
            deadline = dt_parser.parse(t.deadline_iso) if t.deadline_iso else None
            vec = embedding.embed(f"{t.title}\n{t.expected_outcomes or ''}\n{t.scope or ''}")

            existing = db.scalars(select(Topic).where(Topic.topic_id == t.topic_id)).first()
            if existing:
                existing.source = t.source
                existing.title = t.title
                existing.cluster = t.cluster
                existing.action_type = t.action_type
                existing.trl_min = t.trl_min
                existing.trl_max = t.trl_max
                existing.expected_outcomes = t.expected_outcomes
                existing.scope = t.scope
                existing.budget_total = t.budget_total
                existing.deadline = deadline
                existing.status = t.status
                existing.topic_url = t.topic_url
                existing.metadata_json = t.metadata_json
                existing.embedding = vec
            else:
                db.add(Topic(
                    source=t.source,
                    topic_id=t.topic_id,
                    title=t.title,
                    cluster=t.cluster,
                    action_type=t.action_type,
                    trl_min=t.trl_min,
                    trl_max=t.trl_max,
                    expected_outcomes=t.expected_outcomes,
                    scope=t.scope,
                    budget_total=t.budget_total,
                    deadline=deadline,
                    status=t.status,
                    topic_url=t.topic_url,
                    metadata_json=t.metadata_json,
                    embedding=vec,
                ))
            total_topics += 1

    db.commit()
    return {'topics_upserted': total_topics, 'snapshots_saved': total_snapshots}


def list_topics(db: Session):
    return db.scalars(select(Topic).order_by(Topic.deadline.asc().nulls_last())).all()
