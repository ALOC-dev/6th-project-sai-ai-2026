"""오류 본문은 항상 {"code": ..., "message": ...} (11/8 BE 합의)."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.codes import ErrorCode

logger = logging.getLogger("sai_ai")


class AppError(Exception):
    def __init__(self, status_code: int, code: ErrorCode, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: ErrorCode, message: str) -> dict:
    return {"code": code.value, "message": message}


def _validation_message(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "잘못된 요청입니다."
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = first.get("msg", "invalid")
    return f"{loc}: {msg}" if loc else msg


_HTTP_CODE_MAP = {
    401: ErrorCode.UNAUTHORIZED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400, content=error_body(ErrorCode.INVALID_INPUT, _validation_message(exc))
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _HTTP_CODE_MAP.get(exc.status_code, ErrorCode.INVALID_INPUT if exc.status_code < 500 else ErrorCode.INTERNAL_ERROR)
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        # 스택은 서버 로그에만 남기고, 응답에는 내부 정보를 노출하지 않는다.
        logger.exception("unhandled error")
        return JSONResponse(status_code=500, content=error_body(ErrorCode.INTERNAL_ERROR, "서버 오류가 발생했습니다."))
