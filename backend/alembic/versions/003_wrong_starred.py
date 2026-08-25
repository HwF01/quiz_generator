"""wrong_questions.is_starred for pin-to-top

Revision ID: 003_wrong_starred
Revises: 002_fk_jsonb
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_wrong_starred"
down_revision: Union[str, None] = "002_fk_jsonb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wrong_questions",
        sa.Column("is_starred", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("wrong_questions", "is_starred")
