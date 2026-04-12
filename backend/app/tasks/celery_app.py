from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery = Celery('horizon_radar', broker=settings.redis_url, backend=settings.redis_url)
celery.conf.timezone = 'UTC'
celery.conf.beat_schedule = {
    'daily-ingestion': {
        'task': 'app.tasks.jobs.daily_ingestion',
        'schedule': crontab(hour=3, minute=0),
    },
    'daily-draft-hunter': {
        'task': 'app.tasks.jobs.daily_draft_hunter',
        'schedule': crontab(hour=4, minute=0),
    },
    'monthly-report': {
        'task': 'app.tasks.jobs.monthly_report',
        'schedule': crontab(hour=6, minute=0, day_of_month='1'),
    },
}
