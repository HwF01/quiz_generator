"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("nickname", sa.String(80), nullable=False, server_default="学习者"),
        sa.Column("avatar_url", sa.Text),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("daily_gen_quota", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="uploaded"),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("extracted_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("parse_error", sa.Text()),
        sa.Column("used_ocr", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("passage_map", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "generation_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("quiz_set_id", postgresql.UUID(as_uuid=False)),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(80), nullable=False, server_default="queued"),
        sa.Column("error", sa.Text()),
        sa.Column("config", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("models_used", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "quiz_sets",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("creator_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("documents.id")),
        sa.Column("generation_job_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("generation_jobs.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(50), nullable=False, server_default="自定义"),
        sa.Column("subject", sa.String(50), nullable=False, server_default="general"),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("source_doc_url", sa.Text()),
        sa.Column("question_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_difficulty", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("plays", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blueprint", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("quiz_set_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False, server_default="single_choice"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB()),
        sa.Column("answer", postgresql.JSONB(), nullable=False),
        sa.Column("explanation", sa.Text()),
        sa.Column("distractor_rationale", postgresql.JSONB()),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("knowledge_tags", postgresql.ARRAY(sa.String())),
        sa.Column("micro_skill", sa.String(40), nullable=False, server_default="detail"),
        sa.Column("cognitive_level", sa.String(40), nullable=False, server_default="remember"),
        sa.Column("source_span", postgresql.JSONB()),
        sa.Column("quality_scores", postgresql.JSONB()),
        sa.Column("needs_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_chunk_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "play_records",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quiz_set_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("quiz_sets.id"), nullable=False),
        sa.Column("answers", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("skill_results", postgresql.JSONB()),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("time_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mode", sa.String(30), nullable=False, server_default="sequential"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "wrong_questions",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quiz_set_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("quiz_sets.id"), nullable=False),
        sa.Column("wrong_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_wrong_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "question_id"),
    )
    op.create_table(
        "favorites",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quiz_set_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "quiz_set_id"),
    )
    op.create_table(
        "quiz_ratings",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quiz_set_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("quiz_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "quiz_set_id"),
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])
    op.create_index("ix_questions_quiz_set_id", "questions", ["quiz_set_id"])


def downgrade() -> None:
    op.drop_table("quiz_ratings")
    op.drop_table("favorites")
    op.drop_table("wrong_questions")
    op.drop_table("play_records")
    op.drop_table("questions")
    op.drop_table("quiz_sets")
    op.drop_table("generation_jobs")
    op.drop_table("documents")
    op.drop_table("users")
