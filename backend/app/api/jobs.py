from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.exceptions import AppError, ok
from app.core.redis import get_redis
from app.db.session import get_db
from app.models.generation_job import GenerationJob
from app.models.user import User

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(GenerationJob, job_id)
    if not job or job.user_id != user.id:
        raise AppError("任务不存在", code=404, status_code=404)
    cached: dict = {}
    try:
        redis = get_redis()
        cached = await redis.hgetall(f"job:{job.id}")
    except Exception:
        cached = {}
    return ok(
        {
            "id": job.id,
            "status": cached.get("status") or job.status,
            "progress": int(cached.get("progress") or job.progress or 0),
            "stage": cached.get("stage") or job.stage,
            "error": cached.get("error") or job.error,
            "quiz_set_id": cached.get("quiz_set_id") or job.quiz_set_id,
            "models_used": job.models_used,
        }
    )
