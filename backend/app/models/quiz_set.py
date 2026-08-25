from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class QuizSet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "quiz_sets"

    creator_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id"), nullable=True
    )
    generation_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("generation_jobs.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="自定义")
    subject: Mapped[str] = mapped_column(String(50), default="general")
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="draft")
    source_doc_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    likes: Mapped[int] = mapped_column(Integer, default=0)
    plays: Mapped[int] = mapped_column(Integer, default=0)
    blueprint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
