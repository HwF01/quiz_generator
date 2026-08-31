from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MicroSkill = Literal["gist", "detail", "inference", "cohesion", "theme", "attitude"]
QuestionType = Literal[
    "single_choice",
    "multi_choice",
    "true_false",
    "fill_blank",
    "application",
    "proof",
    "short_answer",
]
Difficulty = Literal["easy", "medium", "hard"]
AllocationMode = Literal["auto", "manual"]
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
SUBJECT_TAGS = frozenset({"humanities", "science", "engineering", "it", "math", "logic"})
QUESTION_TYPES = frozenset(
    {
        "single_choice",
        "multi_choice",
        "true_false",
        "fill_blank",
        "application",
        "proof",
        "short_answer",
    }
)


class QuizBlueprint(BaseModel):
    total_questions: int = Field(default=12, ge=1, le=50)
    allocation_mode: AllocationMode = "auto"
    type_counts: dict[str, int] = Field(default_factory=dict)
    type_mix: dict[str, float] = Field(
        default_factory=lambda: {
            "single_choice": 0.65,
            "multi_choice": 0.15,
            "true_false": 0.2,
        }
    )
    max_detail_ratio: float = Field(default=0.3, ge=0.1, le=1.0)
    target_grade: str = "通用"
    subject_tags: list[str] = Field(default_factory=list)
    target_difficulty: Difficulty | None = None
    enable_web_search: bool = False
    difficulty_mix: dict[str, float] = Field(
        default_factory=lambda: {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    )

    @field_validator("type_counts")
    @classmethod
    def validate_type_counts(cls, value: dict[str, int]) -> dict[str, int]:
        invalid = set(value) - QUESTION_TYPES
        if invalid:
            raise ValueError(f"不支持的题型：{', '.join(sorted(invalid))}")
        if any(not isinstance(count, int) or isinstance(count, bool) or count < 0 for count in value.values()):
            raise ValueError("题型数量必须是非负整数")
        return value

    @field_validator("subject_tags")
    @classmethod
    def validate_subject_tags(cls, value: list[str]) -> list[str]:
        invalid = set(value) - SUBJECT_TAGS
        if invalid:
            raise ValueError(f"不支持的学科标签：{', '.join(sorted(invalid))}")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def validate_manual_counts(self):
        if self.allocation_mode == "manual":
            if not self.type_counts:
                raise ValueError("手动分配至少需要指定一种题型")
            if sum(self.type_counts.values()) != self.total_questions:
                raise ValueError("各题型数量之和必须等于总题量")
        return self


class GenerateQuizIn(BaseModel):
    document_id: str
    title: str = Field(default="未命名题库", max_length=200)
    category: str = Field(default="自定义", max_length=50)
    subject: str = Field(default="auto", max_length=50)
    visibility: Literal["private", "public"] = "private"
    blueprint: QuizBlueprint = Field(default_factory=QuizBlueprint)
    force: bool = False


class RetryQuizIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=50)
    subject: str | None = Field(default=None, max_length=50)
    visibility: Literal["private", "public"] | None = None
    blueprint: QuizBlueprint | None = None
    force: bool | None = None


class GenerationPreviewIn(BaseModel):
    blueprint: QuizBlueprint = Field(default_factory=QuizBlueprint)
    subject: str = Field(default="auto", max_length=50)


class QuestionUpdateIn(BaseModel):
    content: str | None = None
    options: list | None = None
    answer: dict | None = None
    explanation: str | None = None
    subparts: list[dict] | None = None
    external_sources: list[dict] | None = None
    needs_review: bool | None = None

    @field_validator("external_sources")
    @classmethod
    def validate_external_sources(cls, value: list[dict] | None) -> list[dict] | None:
        if value is None:
            return value
        for source in value:
            if not isinstance(source, dict):
                raise ValueError("外部参考来源格式不正确")
            if not all(str(source.get(key) or "").strip() for key in ("id", "title", "url", "excerpt")):
                raise ValueError("外部参考来源缺少必要信息")
            if not str(source["url"]).startswith(("https://", "http://")):
                raise ValueError("外部参考来源仅支持 HTTP(S) 地址")
        return value


class QuizUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    visibility: Literal["private", "public"] | None = None
    category: str | None = None


class PlaySubmitIn(BaseModel):
    answers: dict[str, str | list[str] | dict[str, str]]
    time_spent: int = 0
    mode: str = "sequential"
    question_ids: list[str] | None = None


class PlayAnswerUpdateIn(BaseModel):
    answer: str | dict[str, str]


class RatingIn(BaseModel):
    score: int = Field(ge=1, le=5)
    comment: str | None = None
