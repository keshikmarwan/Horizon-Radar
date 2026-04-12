from sqlalchemy import Integer, Float, DateTime, ForeignKey, func, Text, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TopicMatch(Base):
    __tablename__ = 'topic_matches'
    __table_args__ = (UniqueConstraint('profile_id', 'topic_id', name='uq_profile_topic'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('company_profiles.id', ondelete='CASCADE'), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id', ondelete='CASCADE'), index=True)
    semantic_score: Mapped[float] = mapped_column(Float)
    adjusted_score: Mapped[float] = mapped_column(Float, index=True)
    recommendation: Mapped[str] = mapped_column(Text)
    gaps: Mapped[str] = mapped_column(Text)
    evidence_snippets: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
