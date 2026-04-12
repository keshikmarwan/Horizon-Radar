from sqlalchemy import Integer, String, DateTime, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FetchSnapshot(Base):
    __tablename__ = 'fetch_snapshots'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(120), index=True)
    source_url: Mapped[str] = mapped_column(String(1200))
    local_path: Mapped[str] = mapped_column(String(1200))
    content_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    content_type: Mapped[str] = mapped_column(String(100))
    fetched_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
