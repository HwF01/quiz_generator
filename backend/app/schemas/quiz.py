from typing import Literal

from pydantic import BaseModel, Field

MicroSkill = Literal["gist", "detail", "inference", "cohesion", "theme", "attitude"]
QuestionType = Literal["single_choice", "multi_choice", "true_false", "fill_blank"]
Difficulty = Literal["easy", "medium", "hard"]
Subject = Literal[
    "general",
    "civics",
    "history",
    "exam_civil",
    "exam_grad",
    "it",
    "math",
    "logic",
]


class QuizBlueprint(BaseModel):
    total_questions: int = Field(default=12, ge=1, le=40)
    type_mix: dict[str, float] = Field(
        default_factory=lambda: {
            "single_choice": 0.8,
            "true_false": 0.2,
        }
    )
    max_detail_ratio: float = Field(default=0.3, ge=0.1, le=1.0)
    target_grade: str = "通用"
    difficulty_mix: dict[str, float] = Field(
        default_factory=lambda: {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    )


class GenerateQuizIn(BaseModel):
    document_id: str
    title: str = Field(default="未命名题库", max_length=200)
    category: str = Field(default="自定义", max_length=50)
    subject: str = Field(default="auto", max_length=50)
    visibility: Literal["private", "public"] = "private"
    blueprint: QuizBlueprint = Field(default_factory=QuizBlueprint)
    force: bool = False


class QuestionUpdateIn(BaseModel):
    content: str | None = None
    options: list | None = None
    answer: dict | None = None
    explanation: str | None = None
    needs_review: bool | None = None


class QuizUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    visibility: Literal["private", "public"] | None = None
    category: str | None = None


class PlaySubmitIn(BaseModel):
    answers: dict[str, str | list[str]]
    time_spent: int = 0
    mode: str = "sequential"
    question_ids: list[str] | None = None


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None
