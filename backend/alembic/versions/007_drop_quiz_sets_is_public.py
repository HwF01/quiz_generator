"""drop quiz_sets.is_public; visibility is the single source

Revision ID: 007_drop_quiz_sets_is_public
Revises: 006_list_query_indexes
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_drop_quiz_sets_is_public"
down_revision: Union[str, None] = "006_list_query_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE quiz_sets SET visibility = 'public' "
            "WHERE is_public IS TRUE AND visibility IS DISTINCT FROM 'public'"
        )
    )
    op.drop_column("quiz_sets", "is_public")


def downgrade() -> None:
    op.add_column(
        "quiz_sets",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute(sa.text("UPDATE quiz_sets SET is_public = TRUE WHERE visibility = 'public'"))
