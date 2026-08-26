from sqlalchemy import ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class QuestionFavorite(TimestampMixin, Base):
    __tablename__ = "question_favorites"
    __table_args__ = (PrimaryKeyConstraint("user_id", "question_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="CASCADE")
    )
    quiz_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_sets.id", ondelete="CASCADE")
    )
