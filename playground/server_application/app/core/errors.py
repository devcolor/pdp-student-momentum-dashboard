"""One JSON shape for every error the API returns:

    {"error": {"status": 404, "code": "not_found", "message": "...", "path": "/api/v1/..."}}

Unknown endpoints also get a pointer to the docs (outside production). Unexpected exceptions are
logged in full on the server and reach the client only as a generic message.
"""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


class ErrorBody(BaseModel):
    status: int
    code: str
    message: str
    path: str
    details: list[Any] | None = None
    docs: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


def _error_code_for_status(status: int) -> str:
    """404 -> "not_found", 503 -> "service_unavailable"."""
    try:
        return HTTPStatus(status).phrase.lower().replace(" ", "_").replace("-", "_")
    except ValueError:
        return "error"


def _error_response(body: ErrorBody, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=body.status,
        content=jsonable_encoder(ErrorResponse(error=body), exclude_none=True),
        headers=headers,
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Starlette raises 404 "Not Found" when no route matches; routes raise their own messages.
    no_route_matched = exc.status_code == 404 and exc.detail == "Not Found"
    message = (
        f"No endpoint matches {request.method} {request.url.path}."
        if no_route_matched
        else str(exc.detail)
    )
    body = ErrorBody(
        status=exc.status_code,
        code=_error_code_for_status(exc.status_code),
        message=message,
        path=request.url.path,
        docs=settings.docs_path if no_route_matched else None,
    )
    return _error_response(body, headers=getattr(exc, "headers", None))


def _serializable(error: dict[str, Any]) -> dict[str, Any]:
    """One pydantic error, with anything in ctx that JSON can't hold written as text.

    A model validator that raises ValueError puts the exception itself in ctx, which no encoder
    can serialize, so the whole 422 would fail to render.
    """
    ctx = error.get("ctx")
    if not ctx:
        return error
    return {**error, "ctx": {key: str(value) for key, value in ctx.items()}}


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    body = ErrorBody(
        status=422,
        code="validation_error",
        message="The request was not valid. See details for each field.",
        path=request.url.path,
        details=[_serializable(error) for error in exc.errors()],
    )
    return _error_response(body)


async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    body = ErrorBody(
        status=500,
        code="internal_error",
        message="Something went wrong on our side. Please try again.",
        path=request.url.path,
    )
    return _error_response(body)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
