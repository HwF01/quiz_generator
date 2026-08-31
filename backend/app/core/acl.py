from __future__ import annotations

from app.core.exceptions import AppError
from app.models.quiz_set import QuizSet
from app.models.user import User

SEED_EMAIL = "system@example.com"
LEGACY_SEED_EMAILS = frozenset({"system@quiz.local", "system@quiz.example"})


def quiz_is_accessible(quiz: QuizSet | None, user: User | None) -> bool:
    if quiz is None:
        return False
    if quiz.visibility == "public" or quiz.is_builtin:
        return True
    if user is not None and quiz.creator_id == user.id:
        return True
    return False


def assert_quiz_accessible(quiz: QuizSet | None, user: User | None) -> QuizSet:
    """Private quizzes look like missing resources so UUID probing yields 404."""
    if not quiz_is_accessible(quiz, user):
        raise AppError("题库不存在", code=404, status_code=404)
    assert quiz is not None
    return quiz
