from sqlalchemy import ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Favorite(TimestampMixin, Base):
    __tablename__ = "favorites"
    __table_args__ = (PrimaryKeyConstraint("user_id", "quiz_set_id"),)

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    quiz_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("quiz_sets.id", ondelete="CASCADE")
    )
