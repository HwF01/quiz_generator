from app.core.arq import redis_settings
from app.db.session import SessionLocal
from app.services.pipeline import run_generation


async def generate_quiz_job(ctx, job_id: str):
    async with SessionLocal() as db:
        await run_generation(db, job_id)


class WorkerSettings:
    functions = [generate_quiz_job]
    redis_settings = redis_settings()
    max_jobs = 4
    job_timeout = 60 * 20
