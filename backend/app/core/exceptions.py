import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("quizgen")


class AppError(Exception):
    def __init__(self, message: str, code: int = 400, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "data": None, "message": exc.message},
    )


async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "data": None, "message": "服务器繁忙，请稍后重试"},
    )


def ok(data=None, message: str = "ok"):
    return {"code": 0, "data": data, "message": message}
