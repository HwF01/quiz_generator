from sqlalchemy import Boolean, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questions"

    quiz_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_sets.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30), default="single_choice")
    content: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    answer: Mapped[dict] = mapped_column(JSON)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    distractor_rationale: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    knowledge_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    micro_skill: Mapped[str] = mapped_column(String(40), default="detail")
    cognitive_level: Mapped[str] = mapped_column(String(40), default="remember")
    source_span: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quality_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    source_chunk_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
