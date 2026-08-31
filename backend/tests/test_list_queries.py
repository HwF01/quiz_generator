from sqlalchemy import event, select
from httpx import AsyncClient

from app.models.favorite import Favorite
from app.models.play_record import PlayRecord
from app.models.question import Question
from app.models.question_favorite import QuestionFavorite
from app.models.quiz_rating import QuizRating
from app.models.quiz_set import QuizSet
from app.models.wrong_question import WrongQuestion
from tests.conftest import register


def _listen_sql(engine) -> list[str]:
    statements: list[str] = []

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(str(statement))

    sync_engine = getattr(engine, "sync_engine", engine)
    event.listen(sync_engine, "after_cursor_execute", _on_execute)
    return statements


async def _user_id(client: AsyncClient, token: str) -> str:
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    return me.json()["data"]["id"]


async def _seed_public_quizzes(session_factory, creator_id: str, n: int) -> list[QuizSet]:
    quizzes: list[QuizSet] = []
    async with session_factory() as db:
        for i in range(n):
            quiz = QuizSet(
                creator_id=creator_id,
                title=f"公开题库{i}",
                description=f"描述{i}",
                category="常识",
                visibility="public",
                status="ready",
                question_count=1,
                likes=i,
                plays=i,
            )
            db.add(quiz)
            quizzes.append(quiz)
        await db.flush()
        for quiz in quizzes:
            db.add(
                Question(
                    quiz_set_id=quiz.id,
                    type="single_choice",
                    content=f"题{quiz.title}",
                    options=[{"key": "A", "text": "1"}],
                    answer={"keys": ["A"]},
                    micro_skill="detail",
                )
            )
            db.add(QuizRating(user_id=creator_id, quiz_set_id=quiz.id, score=4))
        await db.commit()
        for quiz in quizzes:
            await db.refresh(quiz)
    return quizzes


async def test_plaza_batches_avg_rating(client: AsyncClient, session_factory):
    data = await register(client, "plaza@example.com")
    creator_id = await _user_id(client, data["token"])
    quizzes = await _seed_public_quizzes(session_factory, creator_id, 5)
    async with session_factory() as db:
        statements = _listen_sql(db.get_bind())

    statements.clear()
    res = await client.get("/api/plaza")
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    by_id = {row["id"]: row for row in body["data"]}
    for quiz in quizzes:
        assert by_id[quiz.id]["avg_rating"] == 4.0
        assert by_id[quiz.id]["title"] == quiz.title
    rating_sql = [sql for sql in statements if "quiz_ratings" in sql.lower()]
    assert len(rating_sql) == 1


async def test_favorites_plays_wrong_and_starred_are_batched(
    client: AsyncClient, session_factory
):
    data = await register(client, "lists@example.com")
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await _user_id(client, token)
    quizzes = await _seed_public_quizzes(session_factory, user_id, 5)
    async with session_factory() as db:
        qrows = (await db.execute(select(Question))).scalars().all()
        by_quiz = {question.quiz_set_id: question for question in qrows}
        for quiz in quizzes:
            question = by_quiz[quiz.id]
            db.add(Favorite(user_id=user_id, quiz_set_id=quiz.id))
            db.add(
                PlayRecord(
                    user_id=user_id,
                    quiz_set_id=quiz.id,
                    answers={},
                    score=80,
                    time_spent=12,
                    mode="sequential",
                )
            )
            db.add(
                WrongQuestion(
                    user_id=user_id,
                    question_id=question.id,
                    quiz_set_id=quiz.id,
                    wrong_count=2,
                )
            )
            db.add(
                QuestionFavorite(
                    user_id=user_id,
                    question_id=question.id,
                    quiz_set_id=quiz.id,
                )
            )
        await db.commit()
        statements = _listen_sql(db.get_bind())

    statements.clear()
    favs = await client.get("/api/quizzes/favorites", headers=headers)
    fav_sql = list(statements)
    assert favs.status_code == 200
    fav_data = favs.json()["data"]
    assert {row["title"] for row in fav_data} == {quiz.title for quiz in quizzes}
    assert all(row["favorited"] is True for row in fav_data)
    assert len([s for s in fav_sql if "quiz_sets" in s.lower()]) == 1

    statements.clear()
    plays = await client.get("/api/plays", headers=headers)
    play_sql = list(statements)
    assert plays.status_code == 200
    play_data = plays.json()["data"]
    assert {row["title"] for row in play_data} == {quiz.title for quiz in quizzes}
    assert len(play_data) == 5
    assert len([s for s in play_sql if "play_records" in s.lower()]) == 1

    statements.clear()
    wrongs = await client.get("/api/wrong-questions", headers=headers)
    wrong_sql = list(statements)
    assert wrongs.status_code == 200
    wrong_data = wrongs.json()["data"]
    assert len(wrong_data) == 5
    assert {row["quiz"]["title"] for row in wrong_data} == {quiz.title for quiz in quizzes}
    assert all(row["question"]["content"] for row in wrong_data)
    assert len([s for s in wrong_sql if "wrong_questions" in s.lower()]) == 1

    statements.clear()
    stars = await client.get("/api/question-favorites", headers=headers)
    star_sql = list(statements)
    assert stars.status_code == 200
    star_data = stars.json()["data"]
    assert len(star_data) == 5
    assert {row["quiz"]["title"] for row in star_data} == {quiz.title for quiz in quizzes}
    assert all(row["favorited"] is True for row in star_data)
    assert len([s for s in star_sql if "question_favorites" in s.lower()]) == 1


async def test_my_quizzes_include_favorited(client: AsyncClient, session_factory):
    data = await register(client, "myfav@example.com")
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await _user_id(client, token)
    quizzes = await _seed_public_quizzes(session_factory, user_id, 2)
    async with session_factory() as db:
        db.add(Favorite(user_id=user_id, quiz_set_id=quizzes[0].id))
        await db.commit()
        statements = _listen_sql(db.get_bind())

    statements.clear()
    res = await client.get("/api/quizzes", headers=headers)
    assert res.status_code == 200
    body = {row["id"]: row for row in res.json()["data"]}
    assert body[quizzes[0].id]["favorited"] is True
    assert body[quizzes[1].id]["favorited"] is False
    assert len([s for s in statements if "favorites" in s.lower()]) == 1


async def test_plaza_lists_quiz_with_only_visibility_public(client: AsyncClient, session_factory):
    data = await register(client, "plaza-vis@example.com")
    creator_id = await _user_id(client, data["token"])
    async with session_factory() as db:
        quiz = QuizSet(
            creator_id=creator_id,
            title="仅 visibility 公开",
            status="ready",
            visibility="public",
        )
        db.add(quiz)
        await db.commit()
        quiz_id = quiz.id

    res = await client.get("/api/plaza")
    assert res.status_code == 200
    body = res.json()
    assert body["code"] == 0
    by_id = {row["id"]: row for row in body["data"]}
    assert quiz_id in by_id
    assert by_id[quiz_id]["title"] == "仅 visibility 公开"

    cats = await client.get("/api/plaza/categories")
    assert cats.status_code == 200
    assert any(row["count"] >= 1 for row in cats.json()["data"])


async def test_patch_visibility_roundtrips_plaza(client: AsyncClient, session_factory):
    data = await register(client, "plaza-patch@example.com")
    token = data["token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = await _user_id(client, token)
    async with session_factory() as db:
        quiz = QuizSet(
            creator_id=user_id,
            title="审校后公开",
            status="ready",
            visibility="private",
        )
        db.add(quiz)
        await db.flush()
        db.add(
            Question(
                quiz_set_id=quiz.id,
                type="single_choice",
                content="已审校题",
                options=[
                    {"key": "A", "text": "对"},
                    {"key": "B", "text": "错1"},
                    {"key": "C", "text": "错2"},
                    {"key": "D", "text": "错3"},
                ],
                answer={"keys": ["A"]},
                micro_skill="detail",
                needs_review=False,
            )
        )
        await db.commit()
        quiz_id = quiz.id

    published = await client.patch(
        f"/api/quizzes/{quiz_id}",
        headers=headers,
        json={"visibility": "public"},
    )
    assert published.status_code == 200
    pub_body = published.json()["data"]
    assert pub_body["visibility"] == "public"
    assert pub_body["is_public"] is True

    plaza = await client.get("/api/plaza")
    assert any(row["id"] == quiz_id for row in plaza.json()["data"])

    hidden = await client.patch(
        f"/api/quizzes/{quiz_id}",
        headers=headers,
        json={"visibility": "private"},
    )
    assert hidden.status_code == 200
    hid_body = hidden.json()["data"]
    assert hid_body["visibility"] == "private"
    assert hid_body["is_public"] is False

    plaza_after = await client.get("/api/plaza")
    assert all(row["id"] != quiz_id for row in plaza_after.json()["data"])
