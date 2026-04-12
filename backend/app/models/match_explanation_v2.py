from sqlalchemy import DateTime, ForeignKey, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MatchExplanationV2(Base):
    __tablename__ = 'match_explanations_v2'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_result_id: Mapped[int] = mapped_column(ForeignKey('match_results_v2.id', ondelete='CASCADE'), unique=True, index=True)
    supporting_topic_sections: Mapped[list[dict]] = mapped_column(JSON, default=list)
    supporting_profile_sections: Mapped[list[dict]] = mapped_column(JSON, default=list)
    must_have_gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    nice_to_have_gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_partner_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    suggested_actions: Mapped[list[str]] = mapped_column(JSON, default=list)
    why_fit: Mapped[list[str]] = mapped_column(JSON, default=list)
    why_not_fit: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
