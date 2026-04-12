from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.company_profile import CompanyProfile
from app.services.draft_hunter_service import run_draft_hunter
from app.services.ingestion_service import ingest_calls
from app.services.matching_service import recompute_matches
from app.services.report_service import generate_monthly_report
from app.tasks.celery_app import celery


@celery.task
def daily_ingestion():
    db = SessionLocal()
    try:
        result = ingest_calls(db)
        profiles = db.query(CompanyProfile).all()
        for p in profiles:
            recompute_matches(db, p.id)
        return result
    finally:
        db.close()


@celery.task
def daily_draft_hunter():
    db = SessionLocal()
    try:
        return run_draft_hunter(db)
    finally:
        db.close()


@celery.task
def monthly_report():
    db = SessionLocal()
    try:
        users = db.scalars(select(CompanyProfile.user_id).distinct()).all()
        created = []
        for user_id in users:
            report = generate_monthly_report(db, user_id=user_id)
            created.append({'id': report.id, 'month': report.report_month, 'user_id': user_id})
        return {'reports': created}
    finally:
        db.close()
