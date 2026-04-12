import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.services.matching_service import recompute_matches


SEED_PROFILES = [
    {
        'user_id': 'demo-user',
        'name': 'Industrial AI BU',
        'description': 'We build edge AI systems for predictive maintenance, digital twins and computer vision in manufacturing.',
        'tags': ['AI', 'edge computing', 'manufacturing', 'digital twin'],
        'constraints': {
            'preferred_trl': 6,
            'must_have_keywords': ['manufacturing', 'AI'],
            'avoid_action_types': ['CSA'],
        },
    },
    {
        'user_id': 'demo-user',
        'name': 'Energy Storage BU',
        'description': 'Battery analytics, BMS software and second-life optimization for grid flexibility.',
        'tags': ['battery', 'BMS', 'energy'],
        'constraints': {
            'preferred_trl': 7,
            'must_have_keywords': ['battery', 'energy'],
            'avoid_action_types': [],
        },
    },
]


def main():
    db = SessionLocal()
    try:
        for payload in SEED_PROFILES:
            exists = db.query(CompanyProfile).filter_by(user_id=payload['user_id'], name=payload['name']).first()
            if exists:
                continue
            profile = CompanyProfile(**payload)
            db.add(profile)
        db.commit()

        for p in db.query(CompanyProfile).all():
            recompute_matches(db, p.id)

        print('Seed data loaded.')
    finally:
        db.close()


if __name__ == '__main__':
    main()
