"""fk cascade, knowledge_tags jsonb, job set null

Revision ID: 002_fk_jsonb
Revises: 001_initial
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002_fk_jsonb"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("play_records_quiz_set_id_fkey", "play_records", type_="foreignkey")
    op.create_foreign_key(
        "play_records_quiz_set_id_fkey",
        "play_records",
        "quiz_sets",
        ["quiz_set_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("wrong_questions_quiz_set_id_fkey", "wrong_questions", type_="foreignkey")
    op.create_foreign_key(
        "wrong_questions_quiz_set_id_fkey",
        "wrong_questions",
        "quiz_sets",
        ["quiz_set_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("quiz_sets_generation_job_id_fkey", "quiz_sets", type_="foreignkey")
    op.create_foreign_key(
        "quiz_sets_generation_job_id_fkey",
        "quiz_sets",
        "generation_jobs",
        ["generation_job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_generation_jobs_quiz_set_id",
        "generation_jobs",
        "quiz_sets",
        ["quiz_set_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        "ALTER TABLE questions ALTER COLUMN knowledge_tags TYPE JSONB USING to_jsonb(knowledge_tags)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE questions ALTER COLUMN knowledge_tags TYPE VARCHAR[] "
        "USING ARRAY(SELECT jsonb_array_elements_text(coalesce(knowledge_tags, '[]'::jsonb)))"
    )
    op.drop_constraint("fk_generation_jobs_quiz_set_id", "generation_jobs", type_="foreignkey")
    op.drop_constraint("quiz_sets_generation_job_id_fkey", "quiz_sets", type_="foreignkey")
    op.create_foreign_key(
        "quiz_sets_generation_job_id_fkey",
        "quiz_sets",
        "generation_jobs",
        ["generation_job_id"],
        ["id"],
    )
    op.drop_constraint("wrong_questions_quiz_set_id_fkey", "wrong_questions", type_="foreignkey")
    op.create_foreign_key(
        "wrong_questions_quiz_set_id_fkey",
        "wrong_questions",
        "quiz_sets",
        ["quiz_set_id"],
        ["id"],
    )
    op.drop_constraint("play_records_quiz_set_id_fkey", "play_records", type_="foreignkey")
    op.create_foreign_key(
        "play_records_quiz_set_id_fkey",
        "play_records",
        "quiz_sets",
        ["quiz_set_id"],
        ["id"],
    )
