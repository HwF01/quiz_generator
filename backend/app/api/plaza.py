import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_optional_user
from app.core.exceptions import ok
from app.db.session import get_db
from app.models.favorite import Favorite
from app.models.quiz_rating import QuizRating
from app.models.quiz_set import QuizSet
from app.models.user import User
from app.services.retrieval import SQARetrieval

router = APIRouter(prefix="/plaza", tags=["plaza"])


def _plaza_visible():
    return (
        or_(QuizSet.visibility == "public", QuizSet.is_builtin.is_(True)),
        QuizSet.status == "ready",
    )


@router.get("")
async def plaza(
    q: str | None = None,
    category: str | None = None,
    sort: str = "hot",
    builtin: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    filters = [*_plaza_visible()]
    if category:
        filters.append(QuizSet.category == category)
    if builtin is True:
        filters.append(QuizSet.is_builtin.is_(True))
    if builtin is False:
        filters.append(QuizSet.is_builtin.is_(False))
    if q:
        like = f"%{q}%"
        filters.append(or_(QuizSet.title.ilike(like), QuizSet.description.ilike(like)))
    total = int(await db.scalar(select(func.count(QuizSet.id)).where(*filters)) or 0)
    stmt = select(QuizSet).where(*filters)
    if sort == "new":
        stmt = stmt.order_by(QuizSet.created_at.desc())
    else:
        stmt = stmt.order_by(QuizSet.plays.desc(), QuizSet.likes.desc())
    offset = (page - 1) * page_size
    rows = (await db.execute(stmt.offset(offset).limit(page_size))).scalars().all()

    if q and rows:
        docs = [
            {"id": z.id, "text": f"{z.title} {z.description or ''} {z.category}"}
            for z in rows
        ]
        ranked_ids = await asyncio.to_thread(_plaza_rank_ids, docs, q)
        order = {i: n for n, i in enumerate(ranked_ids)}
        rows = sorted(rows, key=lambda z: order.get(z.id, 999))

    fav_ids = set()
    if user:
        favs = await db.execute(select(Favorite.quiz_set_id).where(Favorite.user_id == user.id))
        fav_ids = set(favs.scalars().all())
    avg_map: dict[str, float] = {}
    ids = [z.id for z in rows]
    if ids:
        avg_rows = await db.execute(
            select(QuizRating.quiz_set_id, func.avg(QuizRating.score))
            .where(QuizRating.quiz_set_id.in_(ids))
            .group_by(QuizRating.quiz_set_id)
        )
        avg_map = {qid: float(avg or 0) for qid, avg in avg_rows.all()}
    out = []
    for z in rows:
        out.append(
            {
                "id": z.id,
                "title": z.title,
                "description": z.description,
                "category": z.category,
                "subject": z.subject,
                "question_count": z.question_count,
                "likes": z.likes,
                "plays": z.plays,
                "is_builtin": z.is_builtin,
                "avg_rating": avg_map.get(z.id, 0.0),
                "favorited": z.id in fav_ids,
            }
        )
    return ok({"items": out, "total": total, "page": page, "page_size": page_size})


def _plaza_rank_ids(docs: list[dict], query: str) -> list[str]:
    return [d["id"] for d in SQARetrieval(docs).search(query, k=len(docs))]


@router.get("/categories")
async def categories(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(QuizSet.category, func.count())
        .where(*_plaza_visible())
        .group_by(QuizSet.category)
    )
    return ok([{"category": c, "count": n} for c, n in rows.all()])
