"""Canonical error envelope and application-wide exception handlers."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("tally.web.errors")


def error_response(
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {}}}
    return JSONResponse(status_code=status, content=body)


class APIError(Exception):
    status: int = 500
    default_code: str = "SERVER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message: str = message
        self.code: str = code or self.default_code
        self.details: dict[str, Any] = details or {}


class NotFound(APIError):
    status = 404
    default_code = "NOT_FOUND"


class Conflict(APIError):
    status = 409
    default_code = "CONFLICT"


class FindingsLocked(Conflict):
    default_code = "FINDING_LOCKED"

    def __init__(
        self,
        conflicting_ids: list[int],
        holders: dict[int, str],
    ) -> None:
        first_id = conflicting_ids[0]
        holder = holders.get(first_id, "unknown")
        super().__init__(
            f"Finding {first_id} is currently held by job {holder}",
            details={
                "conflicting_ids": conflicting_ids,
                "holders": {str(k): v for k, v in holders.items()},
            },
        )


class JobBusyError(Conflict):
    default_code = "JOB_ALREADY_RUNNING"

    def __init__(self, kind: str, current_holder: str) -> None:
        super().__init__(
            f"Job {kind!r} is already running: held by {current_holder}",
            details={"kind": kind, "current_holder": current_holder},
        )


class StaleSavedScan(Conflict):
    default_code = "STALE_SAVED_SCAN"

    def __init__(self, stale_items: list[dict[str, Any]]) -> None:
        super().__init__(
            "Saved scan references items that no longer exist",
            details={"staleItems": stale_items},
        )


class ValidationError(APIError):
    status = 422
    default_code = "VALIDATION_ERROR"


class PathTraversal(APIError):
    status = 400
    default_code = "PATH_TRAVERSAL"


class Forbidden(APIError):
    status = 403
    default_code = "FORBIDDEN"


class Unauthenticated(APIError):
    status = 401
    default_code = "UNAUTHENTICATED"


async def _handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
    return error_response(exc.status, exc.code, exc.message, exc.details)


async def _handle_value_error(_request: Request, exc: ValueError) -> JSONResponse:
    return error_response(422, "VALIDATION_ERROR", str(exc))


async def _handle_file_not_found(
    _request: Request, exc: FileNotFoundError
) -> JSONResponse:
    return error_response(404, "NOT_FOUND", str(exc))


async def _handle_request_validation(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = []
    for e in exc.errors():
        loc = e.get("loc", ())
        parts = [str(p) for p in loc]
        if parts and parts[0] in {"body", "query", "path", "header", "cookie"}:
            parts = parts[1:]
        fields.append({"field": ".".join(parts), "issue": e.get("msg", "")})
    return error_response(
        422,
        "VALIDATION_ERROR",
        "Request validation failed",
        {"fields": fields},
    )


async def _handle_http_exception(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


async def _handle_server_error(_request: Request, exc: Exception) -> JSONResponse:
    request_id = os.urandom(4).hex()
    logger.exception("Unhandled server error [%s]", request_id, exc_info=exc)
    return error_response(
        500,
        "SERVER_ERROR",
        "An internal server error occurred.",
        {"request_id": request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    handlers: list[tuple[Any, Any]] = [
        (APIError, _handle_api_error),
        (ValueError, _handle_value_error),
        (FileNotFoundError, _handle_file_not_found),
        (RequestValidationError, _handle_request_validation),
        (StarletteHTTPException, _handle_http_exception),
        (Exception, _handle_server_error),
    ]
    for exc_type, handler in handlers:
        app.add_exception_handler(exc_type, handler)  # type: ignore[arg-type]
