"""list query indexes for plaza and profile endpoints

Revision ID: 006_list_query_indexes
Revises: 005_subjective_questions_and_ai_grades
Create Date: 2026-08-30
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006_list_query_indexes"
down_revision: Union[str, None] = "005_subjective_questions_and_ai_grades"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_quiz_sets_creator_id", "quiz_sets", ["creator_id"])
    op.create_index("ix_play_records_user_id", "play_records", ["user_id"])
    op.create_index("ix_play_records_quiz_set_id", "play_records", ["quiz_set_id"])
    op.create_index("ix_quiz_ratings_quiz_set_id", "quiz_ratings", ["quiz_set_id"])
    op.create_index("ix_generation_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_generation_jobs_document_id", "generation_jobs", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_document_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_user_id", table_name="generation_jobs")
    op.drop_index("ix_quiz_ratings_quiz_set_id", table_name="quiz_ratings")
    op.drop_index("ix_play_records_quiz_set_id", table_name="play_records")
    op.drop_index("ix_play_records_user_id", table_name="play_records")
    op.drop_index("ix_quiz_sets_creator_id", table_name="quiz_sets")
