"""
全局错误处理：统一异常类与 FastAPI 异常处理器。
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError


# ============================================================
# 异常类
# ============================================================

class AppError(Exception):
    """应用基础异常。"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        detail: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.code = code
        self.detail = detail or {}
        super().__init__(self.message)

    def to_dict(self) -> dict:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "status": self.status_code,
                "detail": self.detail,
            }
        }


class NotFoundError(AppError):
    """资源不存在。"""

    def __init__(self, message: str = "请求的资源不存在", detail: dict | None = None):
        super().__init__(
            message=message,
            status_code=404,
            code="NOT_FOUND",
            detail=detail,
        )


class ValidationError(AppError):
    """数据校验失败。"""

    def __init__(self, message: str = "请求数据校验失败", detail: dict | None = None):
        super().__init__(
            message=message,
            status_code=422,
            code="VALIDATION_ERROR",
            detail=detail,
        )


class ServiceError(AppError):
    """业务逻辑错误。"""

    def __init__(self, message: str = "服务处理失败", detail: dict | None = None):
        super().__init__(
            message=message,
            status_code=500,
            code="SERVICE_ERROR",
            detail=detail,
        )


class AuthError(AppError):
    """认证或权限错误。"""

    def __init__(
        self,
        message: str = "认证失败",
        status_code: int = 401,
        code: str = "AUTH_ERROR",
        detail: dict | None = None,
    ):
        super().__init__(
            message=message,
            status_code=status_code,
            code=code,
            detail=detail,
        )


class RateLimitError(AppError):
    """请求频率限制。"""

    def __init__(self, message: str = "请求过于频繁，请稍后再试", detail: dict | None = None):
        super().__init__(
            message=message,
            status_code=429,
            code="RATE_LIMIT",
            detail=detail,
        )


# ============================================================
# 异常处理器
# ============================================================

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """处理自定义 AppError 及其子类。"""
    logger.warning(
        "AppError | {code} | {status} | {message} | {detail}",
        code=exc.code,
        status=exc.status_code,
        message=exc.message,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """处理 FastAPI 原生 HTTPException。"""
    logger.warning(
        "HTTPException | {status} | {detail}",
        status=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail),
                "status": exc.status_code,
                "detail": {},
            }
        },
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """处理 Pydantic 校验错误。"""
    errors = exc.errors()
    logger.warning(
        "ValidationError | body={body} | errors={errors}",
        body=exc.body,
        errors=errors,
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求数据校验失败",
                "status": 422,
                "detail": {"errors": errors},
            }
        },
    )


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """处理数据库异常。"""
    err_msg = str(exc)
    if len(err_msg) > 150:
        err_msg = err_msg[:150] + "..."
    logger.error("DatabaseError | {exc}", exc=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "DATABASE_ERROR",
                "message": err_msg,
                "status": 500,
                "detail": {},
            }
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未被上述处理器捕获的异常。"""
    err_msg = str(exc)
    if len(err_msg) > 150:
        err_msg = err_msg[:150] + "..."
    logger.error("UnhandledError | {exc}", exc=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "code": 1,
            "message": err_msg,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": err_msg,
                "status": 500,
                "detail": {},
            }
        },
    )


def register_error_handlers(app):
    """将异常处理器注册到 FastAPI 应用。"""
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    # Exception 必须最后注册，因为它捕获所有未处理的异常
    app.add_exception_handler(Exception, unhandled_error_handler)
    return app
