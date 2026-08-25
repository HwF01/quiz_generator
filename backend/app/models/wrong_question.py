from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, PrimaryKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"
    __table_args__ = (PrimaryKeyConstraint("user_id", "question_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE")
    )
    quiz_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_sets.id", ondelete="CASCADE")
    )
    wrong_count: Mapped[int] = mapped_column(Integer, default=1)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    last_wrong_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
