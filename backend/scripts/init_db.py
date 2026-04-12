import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401


def main():
    if engine.dialect.name == 'postgresql':
        with engine.begin() as conn:
            conn.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))

    Base.metadata.create_all(bind=engine)

    # Compatibility patch for existing DBs created before multi-tenant reports.
    with engine.begin() as conn:
        if engine.dialect.name == 'postgresql':
            conn.execute(text("ALTER TABLE monthly_reports ADD COLUMN IF NOT EXISTS user_id VARCHAR(128)"))
            conn.execute(text("UPDATE monthly_reports SET user_id = 'system' WHERE user_id IS NULL"))
        else:
            try:
                conn.execute(text("ALTER TABLE monthly_reports ADD COLUMN user_id VARCHAR(128)"))
            except DatabaseError:
                pass
            conn.execute(text("UPDATE monthly_reports SET user_id = 'system' WHERE user_id IS NULL"))

    print('Database initialized.')


if __name__ == '__main__':
    main()
