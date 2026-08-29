from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PlayRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "play_records"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    quiz_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_sets.id", ondelete="CASCADE"), index=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_grades: Mapped[dict] = mapped_column(JSON, default=dict)
    skill_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    time_spent: Mapped[int] = mapped_column(Integer, default=0)
    mode: Mapped[str] = mapped_column(String(30), default="sequential")
