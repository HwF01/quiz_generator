"""question-level favorites independent of wrong_questions

Revision ID: 004_question_favorites
Revises: 003_wrong_starred
Create Date: 2026-08-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_question_favorites"
down_revision: Union[str, None] = "003_wrong_starred"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_favorites",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "question_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "quiz_set_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("quiz_sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "question_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO question_favorites (user_id, question_id, quiz_set_id, created_at) "
            "SELECT user_id, question_id, quiz_set_id, CURRENT_TIMESTAMP "
            "FROM wrong_questions WHERE is_starred IS TRUE "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.drop_table("question_favorites")
