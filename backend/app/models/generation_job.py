from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class GenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "generation_jobs"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), index=True
    )
    quiz_set_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "quiz_sets.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_generation_jobs_quiz_set_id",
        ),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    models_used: Mapped[dict | None] = mapped_column(JSON, nullable=True)
