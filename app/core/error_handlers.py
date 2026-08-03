"""FastAPI exception handlers with privacy-safe client responses."""

from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import ApplicationError
from app.schemas.errors import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def _response(
    code: str, message: str, request_id: str, status_code: int
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, request_id=request_id)
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def application_error_handler(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    return _response(exc.code, exc.safe_message, _request_id(request), exc.status_code)


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Validation internals may contain user content, so return a stable generic message.
    return _response(
        "REQUEST_VALIDATION_ERROR",
        "The request data is invalid.",
        _request_id(request),
        422,
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "event=unexpected_application_error request_id=%s error_type=%s",
        _request_id(request),
        type(exc).__name__,
    )
    return _response(
        "INTERNAL_SERVER_ERROR",
        "An unexpected internal error occurred.",
        _request_id(request),
        500,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
