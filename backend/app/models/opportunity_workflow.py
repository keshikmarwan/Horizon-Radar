from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OpportunityWorkflow(Base):
    __tablename__ = 'opportunity_workflows'
    __table_args__ = (UniqueConstraint('user_id', 'profile_id', 'topic_id', name='uq_workflow_user_profile_topic'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey('company_profiles.id', ondelete='CASCADE'), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey('topics.id', ondelete='CASCADE'), index=True)
    stage: Mapped[str] = mapped_column(String(40), index=True)
    priority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

