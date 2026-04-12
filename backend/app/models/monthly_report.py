from sqlalchemy import Integer, String, DateTime, func, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MonthlyReport(Base):
    __tablename__ = 'monthly_reports'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    report_month: Mapped[str] = mapped_column(String(7), index=True)
    html_path: Mapped[str] = mapped_column(String(1200))
    pdf_path: Mapped[str | None] = mapped_column(String(1200))
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
