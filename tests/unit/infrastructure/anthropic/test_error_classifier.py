import pytest

from infrastructure.anthropic.error_classifier import (
    ErrorClass,
    classify,
    is_resumable,
    requires_user_action,
)


class _StubError(Exception):
    def __init__(self, status_code=None):
        super().__init__("stub")
        self.status_code = status_code


class RateLimitError(_StubError):
    pass


class AuthenticationError(_StubError):
    pass


class PermissionDeniedError(_StubError):
    pass


class APIConnectionError(_StubError):
    pass


class APITimeoutError(_StubError):
    pass


class APIError(_StubError):
    pass


class BadRequestError(_StubError):
    pass


class APIStatusError(_StubError):
    pass


class OverloadedError(_StubError):
    pass


class InternalServerError(_StubError):
    pass


@pytest.mark.parametrize(
    "billing_method, expected",
    [
        ("plan", ErrorClass.RATE_LIMIT_PLAN),
        ("api", ErrorClass.RATE_LIMIT_API),
        (None, ErrorClass.RATE_LIMIT_API),
    ],
)
def test_rate_limit_uses_billing_method(billing_method, expected):
    assert classify(RateLimitError(status_code=429), billing_method) == expected


@pytest.mark.parametrize(
    "billing_method, expected",
    [
        ("plan", ErrorClass.RATE_LIMIT_PLAN),
        ("api", ErrorClass.RATE_LIMIT_API),
    ],
)
def test_429_status_uses_billing_method(billing_method, expected):
    assert classify(_StubError(status_code=429), billing_method) == expected


def test_auth_errors_classified():
    assert classify(AuthenticationError()) == ErrorClass.AUTH_FAILURE
    assert classify(PermissionDeniedError()) == ErrorClass.AUTH_FAILURE
    assert classify(_StubError(status_code=401)) == ErrorClass.AUTH_FAILURE
    assert classify(_StubError(status_code=403)) == ErrorClass.AUTH_FAILURE


def test_network_errors_classified():
    assert classify(APIConnectionError()) == ErrorClass.TRANSIENT_NETWORK
    assert classify(APITimeoutError()) == ErrorClass.TRANSIENT_NETWORK
    assert classify(_StubError(status_code=503)) == ErrorClass.TRANSIENT_NETWORK


def test_model_errors_classified():
    assert classify(APIError()) == ErrorClass.MODEL_ERROR
    assert classify(BadRequestError()) == ErrorClass.MODEL_ERROR
    assert classify(APIStatusError()) == ErrorClass.MODEL_ERROR


def test_none_and_unknown_classified_unknown():
    assert classify(None) == ErrorClass.UNKNOWN
    assert classify(ValueError("boom")) == ErrorClass.UNKNOWN


def test_dict_rate_limit_uses_billing_method():
    assert (
        classify({"type": "rate_limit_error"}, billing_method="plan")
        == ErrorClass.RATE_LIMIT_PLAN
    )
    assert (
        classify({"type": "rate_limit_error"}, billing_method="api")
        == ErrorClass.RATE_LIMIT_API
    )
    assert (
        classify({"status_code": 429}, billing_method="plan")
        == ErrorClass.RATE_LIMIT_PLAN
    )


def test_dict_authentication_error():
    assert classify({"type": "authentication_error"}) == ErrorClass.AUTH_FAILURE
    assert classify({"status_code": 401}) == ErrorClass.AUTH_FAILURE


def test_dict_nested_error_block():
    assert (
        classify({"error": {"type": "rate_limit_error"}}, billing_method="plan")
        == ErrorClass.RATE_LIMIT_PLAN
    )


def test_dict_network_error():
    assert classify({"type": "api_timeout_error"}) == ErrorClass.TRANSIENT_NETWORK
    assert classify({"status_code": 502}) == ErrorClass.TRANSIENT_NETWORK


def test_dict_unknown():
    assert classify({"nope": True}) == ErrorClass.UNKNOWN


def test_is_resumable_matrix():
    resumable = {
        ErrorClass.RATE_LIMIT_PLAN,
        ErrorClass.RATE_LIMIT_API,
        ErrorClass.TRANSIENT_NETWORK,
    }
    for cls in ErrorClass:
        assert is_resumable(cls) == (cls in resumable)


def test_requires_user_action_only_auth():
    for cls in ErrorClass:
        assert requires_user_action(cls) == (cls == ErrorClass.AUTH_FAILURE)


def test_dict_nested_envelope_rate_limit():
    payload = {"type": "error", "error": {"type": "rate_limit_error"}}
    assert classify(payload, billing_method="plan") == ErrorClass.RATE_LIMIT_PLAN


def test_dict_nested_envelope_authentication():
    payload = {"type": "error", "error": {"type": "authentication_error"}}
    assert classify(payload) == ErrorClass.AUTH_FAILURE


def test_dict_overloaded_error_is_transient_network():
    assert classify({"type": "overloaded_error"}) == ErrorClass.TRANSIENT_NETWORK


def test_overloaded_exception_is_transient_network():
    assert classify(OverloadedError()) == ErrorClass.TRANSIENT_NETWORK


def test_internal_server_error_name_is_transient_network():
    assert classify(InternalServerError()) == ErrorClass.TRANSIENT_NETWORK


def test_rate_limit_name_with_auth_status_classes_as_auth():
    assert classify(RateLimitError(status_code=401)) == ErrorClass.AUTH_FAILURE
