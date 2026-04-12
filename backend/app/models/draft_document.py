from sqlalchemy import Integer, String, DateTime, func, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DraftDocument(Base):
    __tablename__ = 'draft_documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(String(800))
    source_url: Mapped[str] = mapped_column(String(1200), index=True)
    file_url: Mapped[str | None] = mapped_column(String(1200))
    version_label: Mapped[str | None] = mapped_column(String(100))
    local_pdf_path: Mapped[str | None] = mapped_column(String(1200))
    text_excerpt: Mapped[str | None] = mapped_column(Text)
    diff_summary: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    discovered_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
