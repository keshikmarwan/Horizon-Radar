from sqlalchemy import String, Text, Integer, DateTime, Float, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Topic(Base):
    __tablename__ = 'topics'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    topic_id: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(700))
    cluster: Mapped[str | None] = mapped_column(String(200), index=True)
    action_type: Mapped[str | None] = mapped_column(String(200), index=True)
    trl_min: Mapped[int | None] = mapped_column(Integer)
    trl_max: Mapped[int | None] = mapped_column(Integer)
    expected_outcomes: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    budget_total: Mapped[float | None] = mapped_column(Float)
    deadline: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str | None] = mapped_column(String(80), index=True)
    topic_url: Mapped[str | None] = mapped_column(String(1000))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(JSON)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
