from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.generation_job import GenerationJob


async def set_progress(db: AsyncSession, job: GenerationJob, progress: int, stage: str, status: str | None = None):
    job.progress = progress
    job.stage = stage
    if status:
        job.status = status
    await db.commit()
    try:
        redis = get_redis()
        await redis.hset(
            f"job:{job.id}",
            mapping={
                "progress": str(progress),
                "stage": stage,
                "status": job.status,
                "error": job.error or "",
                "quiz_set_id": job.quiz_set_id or "",
            },
        )
        await redis.expire(f"job:{job.id}", 60 * 60 * 6)
    except Exception:
        pass
