from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchResultV2(Base):
    __tablename__ = 'match_results_v2'
    __table_args__ = (
        UniqueConstraint('profile_id', 'topic_id', 'model_version', name='uq_match_v2_profile_topic_model'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('company_profiles.id', ondelete='CASCADE'), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id', ondelete='CASCADE'), index=True)
    eligibility_fit: Mapped[float] = mapped_column(Float)
    thematic_fit: Mapped[float] = mapped_column(Float)
    impact_fit: Mapped[float] = mapped_column(Float)
    implementation_fit: Mapped[float] = mapped_column(Float)
    consortium_fit: Mapped[float] = mapped_column(Float)
    data_ai_fit: Mapped[float] = mapped_column(Float)
    evidence_strength: Mapped[float] = mapped_column(Float)
    overall_fit: Mapped[float] = mapped_column(Float, index=True)
    gap_score: Mapped[float] = mapped_column(Float)
    readiness_score: Mapped[float] = mapped_column(Float)
    partner_dependency_score: Mapped[float] = mapped_column(Float)
    submission_priority: Mapped[float] = mapped_column(Float, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(32), index=True)
    recommended_role: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(80), index=True)
    generated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
