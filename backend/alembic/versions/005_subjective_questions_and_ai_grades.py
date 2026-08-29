"""subjective question structure, sources, and AI grades

Revision ID: 005_subjective_questions_and_ai_grades
Revises: 004_question_favorites
Create Date: 2026-08-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_subjective_questions_and_ai_grades"
down_revision: Union[str, None] = "004_question_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("subparts", postgresql.JSONB(), nullable=True))
    op.add_column("questions", sa.Column("external_sources", postgresql.JSONB(), nullable=True))
    op.add_column(
        "play_records",
        sa.Column(
            "ai_grades",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("play_records", "ai_grades")
    op.drop_column("questions", "external_sources")
    op.drop_column("questions", "subparts")
