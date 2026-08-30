from fastapi import APIRouter

from app.api import auth, documents, export, jobs, plays, plaza, quizzes, setup, stats

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(jobs.router)
api_router.include_router(quizzes.router)
api_router.include_router(export.router)
api_router.include_router(plays.router)
api_router.include_router(plaza.router)
api_router.include_router(stats.router)
api_router.include_router(setup.router)
