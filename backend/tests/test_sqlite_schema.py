import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db.sqlite_schema import drop_legacy_quiz_sets_is_public
from app.models.document import Document
from tests.conftest import register


def _column_names(conn) -> list[str]:
    return [row[1] for row in conn.execute(text("PRAGMA table_info(quiz_sets)")).all()]


def _create_legacy_quiz_sets(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE quiz_sets (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                visibility VARCHAR(20) NOT NULL DEFAULT 'private',
                is_public BOOLEAN NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            "INSERT INTO quiz_sets (id, title, visibility, is_public) "
            "VALUES ('1', '公开库', 'private', 1)"
        )
    )


def add_legacy_quiz_sets_is_public(sync_conn) -> None:
    if "is_public" in _column_names(sync_conn):
        return
    sync_conn.execute(text("ALTER TABLE quiz_sets ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT 0"))


def test_legacy_is_public_not_null_rejects_insert(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        _create_legacy_quiz_sets(conn)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError, match="is_public"):
            conn.execute(
                text("INSERT INTO quiz_sets (id, title, visibility) VALUES ('2', '新库', 'private')")
            )
    engine.dispose()


def test_drop_legacy_is_public_backfills_visibility_and_allows_insert(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        _create_legacy_quiz_sets(conn)
    with engine.begin() as conn:
        drop_legacy_quiz_sets_is_public(conn)
        conn.execute(
            text("INSERT INTO quiz_sets (id, title, visibility) VALUES ('2', '新库', 'private')")
        )
        rows = conn.execute(text("SELECT id, title, visibility FROM quiz_sets ORDER BY id")).all()
        assert [(row[0], row[1], row[2]) for row in rows] == [
            ("1", "公开库", "public"),
            ("2", "新库", "private"),
        ]
        assert "is_public" not in _column_names(conn)
    engine.dispose()


async def _noop_generation(_job_id: str) -> None:
    return None


@pytest.mark.asyncio
async def test_generate_succeeds_after_dropping_legacy_is_public(
    client, session_factory, monkeypatch
):
    monkeypatch.setattr("app.api.quizzes._run_generation_job", _noop_generation)
    async with session_factory() as db:
        conn = await db.connection()
        await conn.run_sync(add_legacy_quiz_sets_is_public)
        await conn.run_sync(drop_legacy_quiz_sets_is_public)
        await db.commit()

    registered = await register(client, "legacy-public@example.com")
    token = registered["token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/auth/me", headers=headers)
    user_id = me.json()["data"]["id"]
    async with session_factory() as db:
        doc = Document(
            owner_id=user_id,
            filename="lesson.md",
            content_type="text/markdown",
            object_key="lesson.md",
            size_bytes=12,
            status="parsed",
            extracted_text="叶绿体进行光合作用。",
        )
        db.add(doc)
        await db.commit()
        doc_id = doc.id

    created = await client.post(
        "/api/quizzes/generate",
        headers=headers,
        json={"document_id": doc_id, "title": "旧列删除后应能生成", "blueprint": {"total_questions": 4}},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["quiz_id"]
