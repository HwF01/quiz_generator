from sqlalchemy import ForeignKey, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class QuizRating(TimestampMixin, Base):
    __tablename__ = "quiz_ratings"
    __table_args__ = (PrimaryKeyConstraint("user_id", "quiz_set_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    quiz_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_sets.id", ondelete="CASCADE")
    )
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
