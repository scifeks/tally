"""Classify Anthropic API and Agent SDK errors for retry and failover decisions.

Dict input: if the top-level ``type`` is ``"error"`` and ``error`` is a dict,
the inner dict is unwrapped as the real payload (nested Anthropic envelope).
The ``type`` and ``status_code`` of the effective payload drive classification.

Exception input: the class name and an optional ``status_code`` attribute are
duck-typed so we stay import-free from the anthropic SDK. ``billing_method``
only disambiguates rate-limit errors into plan vs api.

Signal priority (both paths): AUTH > RATE_LIMIT > NETWORK/5xx > MODEL.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal


class ErrorClass(StrEnum):
    RATE_LIMIT_PLAN = "rate_limit_plan"
    RATE_LIMIT_API = "rate_limit_api"
    AUTH_FAILURE = "auth_failure"
    TRANSIENT_NETWORK = "transient_network"
    MODEL_ERROR = "model_error"
    UNKNOWN = "unknown"


BillingMethod = Literal["plan", "api"]


_RESUMABLE = frozenset(
    {
        ErrorClass.RATE_LIMIT_PLAN,
        ErrorClass.RATE_LIMIT_API,
        ErrorClass.TRANSIENT_NETWORK,
    }
)
_USER_ACTION = frozenset({ErrorClass.AUTH_FAILURE})


def is_resumable(error_class: ErrorClass) -> bool:
    return error_class in _RESUMABLE


def requires_user_action(error_class: ErrorClass) -> bool:
    return error_class in _USER_ACTION


def _rate_limit_class(billing_method: BillingMethod | None) -> ErrorClass:
    if billing_method == "plan":
        return ErrorClass.RATE_LIMIT_PLAN
    return ErrorClass.RATE_LIMIT_API


def classify(
    err: Exception | dict[str, Any] | None,
    billing_method: BillingMethod | None = None,
) -> ErrorClass:
    if err is None:
        return ErrorClass.UNKNOWN

    if isinstance(err, dict):
        return _classify_dict(err, billing_method)

    return _classify_exception(err, billing_method)


def _classify_dict(
    payload: dict[str, Any], billing_method: BillingMethod | None
) -> ErrorClass:
    # Unwrap nested Anthropic envelope: {"type": "error", "error": {...}}
    inner = payload.get("error")
    if isinstance(inner, dict) and payload.get("type") in ("error", None):
        payload = inner

    kind = payload.get("type")
    status = payload.get("status_code")

    if kind in ("authentication_error", "permission_error") or status in (401, 403):
        return ErrorClass.AUTH_FAILURE
    if kind == "rate_limit_error" or status == 429:
        return _rate_limit_class(billing_method)
    if kind in ("api_connection_error", "api_timeout_error", "overloaded_error"):
        return ErrorClass.TRANSIENT_NETWORK
    if isinstance(status, int) and 500 <= status < 600:
        return ErrorClass.TRANSIENT_NETWORK
    if kind in ("api_error", "invalid_request_error"):
        return ErrorClass.MODEL_ERROR
    return ErrorClass.UNKNOWN


def _classify_exception(
    err: Exception, billing_method: BillingMethod | None
) -> ErrorClass:
    name = type(err).__name__
    status = getattr(err, "status_code", None)

    if name in ("AuthenticationError", "PermissionDeniedError") or status in (401, 403):
        return ErrorClass.AUTH_FAILURE
    if name == "RateLimitError" or status == 429:
        return _rate_limit_class(billing_method)
    if name in (
        "APIConnectionError",
        "APITimeoutError",
        "OverloadedError",
        "InternalServerError",
    ):
        return ErrorClass.TRANSIENT_NETWORK
    if isinstance(status, int) and 500 <= status < 600:
        return ErrorClass.TRANSIENT_NETWORK
    if name in ("APIError", "BadRequestError", "APIStatusError"):
        return ErrorClass.MODEL_ERROR
    return ErrorClass.UNKNOWN
