from __future__ import annotations

import asyncio
import secrets

from sqlalchemy import select

from app.core.acl import LEGACY_SEED_EMAILS, SEED_EMAIL
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.question import Question
from app.models.quiz_set import QuizSet
from app.models.user import User

BUILTIN = [
    {
        "title": "常识入门：细胞与能量",
        "category": "常识",
        "subject": "general",
        "description": "覆盖细胞器与基础科学常识，适合随堂练习。",
        "questions": [
            {
                "type": "single_choice",
                "content": "光合作用主要发生在植物细胞的哪一结构中？",
                "options": [
                    {"key": "A", "text": "叶绿体"},
                    {"key": "B", "text": "线粒体"},
                    {"key": "C", "text": "核糖体"},
                    {"key": "D", "text": "叶绿体中的线粒体"},
                ],
                "answer": {"keys": ["A"], "texts": ["叶绿体"]},
                "explanation": "光合作用的场所是叶绿体；线粒体负责有氧呼吸。",
                "distractor_rationale": {
                    "B": "同为细胞器，功能不同",
                    "C": "同为亚细胞结构，负责蛋白质合成",
                    "D": "前半句提到叶绿体，后半句偷换主体",
                },
                "difficulty": "medium",
                "micro_skill": "detail",
                "cognitive_level": "remember",
                "knowledge_tags": ["细胞器", "光合作用"],
                "source_span": {"quote": "光合作用发生在叶绿体中"},
                "quality_scores": {"usability": 5, "answer_exists": True},
            },
            {
                "type": "true_false",
                "content": "线粒体是植物细胞进行光合作用的主要场所。",
                "options": [{"key": "true", "text": "正确"}, {"key": "false", "text": "错误"}],
                "answer": {"keys": ["false"]},
                "explanation": "线粒体进行呼吸作用，叶绿体进行光合作用。",
                "difficulty": "easy",
                "micro_skill": "inference",
                "cognitive_level": "understand",
                "knowledge_tags": ["细胞器"],
                "source_span": {"quote": "线粒体负责有氧呼吸"},
                "quality_scores": {"usability": 4, "answer_exists": True},
            },
        ],
    },
    {
        "title": "考公行测：言语理解",
        "category": "考公",
        "subject": "exam_civil",
        "description": "概括主旨与细节辨别练习。",
        "questions": [
            {
                "type": "single_choice",
                "content": "一段材料先列举问题再给出对策，其主旨通常更接近下列哪项？",
                "options": [
                    {"key": "A", "text": "强调问题的严重性并呼吁采取对应措施"},
                    {"key": "B", "text": "仅客观记录若干互不相关的事例"},
                    {"key": "C", "text": "证明该问题在历史上从未出现"},
                    {"key": "D", "text": "说明作者对所有对策都持否定态度"},
                ],
                "answer": {"keys": ["A"], "texts": ["强调问题的严重性并呼吁采取对应措施"]},
                "explanation": "提出问题—分析—对策是行测主旨题常见结构。",
                "distractor_rationale": {
                    "B": "忽略了对策部分",
                    "C": "与材料时间信息不符",
                    "D": "把“讨论对策”偷换成“否定对策”",
                },
                "difficulty": "medium",
                "micro_skill": "theme",
                "cognitive_level": "analyze",
                "knowledge_tags": ["主旨概括"],
                "source_span": {"quote": "提出问题并给出对策"},
                "quality_scores": {"usability": 4, "answer_exists": True},
            }
        ],
    },
    {
        "title": "考研政治：唯物辩证法",
        "category": "考研",
        "subject": "exam_grad",
        "description": "矛盾、量变质变等基本原理。",
        "questions": [
            {
                "type": "single_choice",
                "content": "“过犹不及”主要体现的哲学道理是？",
                "options": [
                    {"key": "A", "text": "要把握事物的度"},
                    {"key": "B", "text": "意识决定物质"},
                    {"key": "C", "text": "否定一切现存事物"},
                    {"key": "D", "text": "外因是变化的根据"},
                ],
                "answer": {"keys": ["A"], "texts": ["要把握事物的度"]},
                "explanation": "度是质和量的统一，超过度就会转化。",
                "distractor_rationale": {
                    "B": "颠倒物质与意识关系",
                    "C": "把辩证否定理解为简单否定",
                    "D": "内外因地位颠倒",
                },
                "difficulty": "medium",
                "micro_skill": "inference",
                "cognitive_level": "understand",
                "knowledge_tags": ["量变质变", "度"],
                "source_span": {"quote": "过犹不及强调把握度"},
                "quality_scores": {"usability": 5, "answer_exists": True},
            }
        ],
    },
    {
        "title": "IT 基础：HTTP 与 REST",
        "category": "IT",
        "subject": "it",
        "description": "Web 开发常见概念辨析。",
        "questions": [
            {
                "type": "single_choice",
                "content": "幂等的 HTTP 方法意味着多次执行与一次执行的效果相同。下列哪项通常被视为幂等？",
                "options": [
                    {"key": "A", "text": "PUT"},
                    {"key": "B", "text": "POST"},
                    {"key": "C", "text": "每次都创建新资源的上传接口"},
                    {"key": "D", "text": "带随机副作用的 webhook"},
                ],
                "answer": {"keys": ["A"], "texts": ["PUT"]},
                "explanation": "PUT 替换指定资源，重复调用结果一致；POST 通常非幂等。",
                "distractor_rationale": {
                    "B": "POST 常用于创建，重复会新增",
                    "C": "描述的是非幂等创建",
                    "D": "副作用破坏幂等",
                },
                "difficulty": "medium",
                "micro_skill": "gist",
                "cognitive_level": "understand",
                "knowledge_tags": ["HTTP", "REST"],
                "source_span": {"quote": "PUT 是幂等方法"},
                "quality_scores": {"usability": 5, "answer_exists": True},
            },
            {
                "type": "fill_blank",
                "content": "在 REST 风格中，使用 ______ 方法更新或替换指定 URI 的完整资源。",
                "options": None,
                "answer": {"texts": ["PUT", "put"]},
                "explanation": "PUT 表示对指定资源的完整替换。",
                "difficulty": "easy",
                "micro_skill": "detail",
                "cognitive_level": "remember",
                "knowledge_tags": ["HTTP"],
                "source_span": {"quote": "PUT 替换指定资源"},
                "quality_scores": {"usability": 4, "answer_exists": True},
            },
        ],
    },
    {
        "title": "中国近代史要点",
        "category": "历史",
        "subject": "history",
        "description": "洋务运动与近代化起步。",
        "questions": [
            {
                "type": "single_choice",
                "content": "洋务运动的口号“中体西用”强调的是？",
                "options": [
                    {"key": "A", "text": "以中学为根本，采用西方技术"},
                    {"key": "B", "text": "彻底废除科举与纲常"},
                    {"key": "C", "text": "以西学为体，中学为用"},
                    {"key": "D", "text": "立即实行君主立宪"},
                ],
                "answer": {"keys": ["A"], "texts": ["以中学为根本，采用西方技术"]},
                "explanation": "中体西用主张在维护纲常的前提下学习西方器物。",
                "distractor_rationale": {
                    "B": "把洋务与维新/革命主张混淆",
                    "C": "体用关系颠倒",
                    "D": "那是维新派的主张方向",
                },
                "difficulty": "medium",
                "micro_skill": "gist",
                "cognitive_level": "understand",
                "knowledge_tags": ["洋务运动"],
                "source_span": {"quote": "中体西用：中学为体，西学为用"},
                "quality_scores": {"usability": 5, "answer_exists": True},
            }
        ],
    },
]


async def seed() -> None:
    async with SessionLocal() as db:
        legacy = await db.scalar(select(User).where(User.email.in_(LEGACY_SEED_EMAILS)))
        if legacy and legacy.email != SEED_EMAIL:
            legacy.email = SEED_EMAIL
            legacy.role = "system"
            await db.flush()
        existing = await db.scalar(select(User).where(User.email == SEED_EMAIL))
        if existing:
            if existing.role != "system":
                existing.role = "system"
            has_builtin = await db.scalar(
                select(QuizSet).where(QuizSet.is_builtin.is_(True)).limit(1)
            )
            if has_builtin:
                await db.commit()
                return
            user = existing
        else:
            user = User(
                email=SEED_EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                nickname="系统题库",
                role="system",
            )
            db.add(user)
            await db.flush()
        for pack in BUILTIN:
            quiz = QuizSet(
                creator_id=user.id,
                title=pack["title"],
                description=pack["description"],
                category=pack["category"],
                subject=pack["subject"],
                visibility="public",
                is_public=True,
                is_builtin=True,
                status="ready",
                question_count=len(pack["questions"]),
            )
            db.add(quiz)
            await db.flush()
            for q in pack["questions"]:
                db.add(
                    Question(
                        quiz_set_id=quiz.id,
                        type=q["type"],
                        content=q["content"],
                        options=q.get("options"),
                        answer=q["answer"],
                        explanation=q.get("explanation"),
                        distractor_rationale=q.get("distractor_rationale"),
                        difficulty=q.get("difficulty", "medium"),
                        knowledge_tags=q.get("knowledge_tags"),
                        micro_skill=q.get("micro_skill", "detail"),
                        cognitive_level=q.get("cognitive_level", "remember"),
                        source_span=q.get("source_span"),
                        quality_scores=q.get("quality_scores"),
                        needs_review=False,
                    )
                )
        await db.commit()
        print("builtin quizzes seeded")


if __name__ == "__main__":
    asyncio.run(seed())
