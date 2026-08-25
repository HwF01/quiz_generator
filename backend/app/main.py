from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import api_router
from app.core.config import settings
from app.core.exceptions import AppError, app_error_handler, ok
from app.core.redis import get_redis
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403
from app.seed import seed
from app.services.storage import ensure_bucket

logger = logging.getLogger("quizgen")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("llm_mode=%s app_env=%s", settings.llm_mode, settings.app_env)
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            def _ensure_wrong_starred(sync_conn):
                from sqlalchemy import inspect

                insp = inspect(sync_conn)
                if not insp.has_table("wrong_questions"):
                    return
                cols = {c["name"] for c in insp.get_columns("wrong_questions")}
                if "is_starred" not in cols:
                    sync_conn.execute(
                        text(
                            "ALTER TABLE wrong_questions ADD COLUMN is_starred "
                            "BOOLEAN NOT NULL DEFAULT 0"
                        )
                    )

            await conn.run_sync(_ensure_wrong_starred)
        await seed()
    try:
        ensure_bucket()
    except Exception:
        logger.exception("ensure_bucket failed")
        if not settings.allow_storage_failure:
            raise
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"code": 422, "data": exc.errors(), "message": "请求参数不正确"},
    )


@app.get("/health")
@app.get("/api/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await get_redis().ping()
    except Exception:
        logger.exception("health check failed")
        return JSONResponse(
            status_code=503,
            content={"code": 503, "data": None, "message": "依赖不可用"},
        )
    return ok({"status": "up", "llm_mode": settings.llm_mode})
