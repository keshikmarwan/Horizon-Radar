import sys
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import select

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.models.topic import Topic
from app.services.embedding_service import EmbeddingService


DEMO_TOPICS = [
    {
        'source': 'demo',
        'topic_id': 'HORIZON-CL4-2026-DIGITAL-01',
        'title': 'AI-enabled resilient manufacturing systems TRL 5-7',
        'cluster': 'CL4',
        'action_type': 'RIA',
        'trl_min': 5,
        'trl_max': 7,
        'expected_outcomes': 'Increase resilience and autonomy of EU manufacturing plants through AI and robotics.',
        'scope': 'Proposals should cover predictive maintenance, digital twins and human-centric automation.',
        'budget_total': 12000000,
        'deadline': datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc),
        'status': 'open',
        'topic_url': 'https://example.org/topic1',
        'metadata_json': {'demo': True},
    },
    {
        'source': 'demo',
        'topic_id': 'HORIZON-CL5-2026-BATTERY-02',
        'title': 'Advanced battery management software for grid-scale storage TRL 6-8',
        'cluster': 'CL5',
        'action_type': 'IA',
        'trl_min': 6,
        'trl_max': 8,
        'expected_outcomes': 'Improve battery life and second-life value chains for grid flexibility.',
        'scope': 'Include AI-based diagnostics, digital battery passport and interoperability APIs.',
        'budget_total': 16000000,
        'deadline': datetime(2026, 10, 12, 17, 0, tzinfo=timezone.utc),
        'status': 'open',
        'topic_url': 'https://example.org/topic2',
        'metadata_json': {'demo': True},
    },
]


def main():
    db = SessionLocal()
    embedder = EmbeddingService()
    try:
        for t in DEMO_TOPICS:
            vec = embedder.embed(f"{t['title']}\n{t['expected_outcomes']}\n{t['scope']}")
            existing = db.scalars(select(Topic).where(Topic.topic_id == t['topic_id'])).first()
            if existing:
                for key, value in t.items():
                    setattr(existing, key, value)
                existing.embedding = vec
            else:
                db.add(Topic(**t, embedding=vec))

        db.commit()
        print('Demo topics loaded.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
