"""Unit tests for web.api._redact."""

from __future__ import annotations

import copy
from urllib.parse import parse_qsl, urlsplit

import pytest

from web.api._redact import REDACTED, redact_config, redact_exempt


def test_top_level_api_key_redacted() -> None:
    assert redact_config({"api_key": "k"}) == {"api_key": REDACTED}


def test_nested_api_key_redacted_model_preserved() -> None:
    result = redact_config({"claude": {"api_key": "k", "model": "opus"}})
    assert result == {"claude": {"api_key": REDACTED, "model": "opus"}}


def test_empty_sensitive_value_redacted() -> None:
    assert redact_config({"api_key": ""}) == {"api_key": REDACTED}


def test_case_insensitive_key() -> None:
    assert redact_config({"API_KEY": "x"}) == {"API_KEY": REDACTED}


def test_auth_block_omitted() -> None:
    payload = {
        "repositories": [{"name": "r", "auth": {"username": "u", "password": "p"}}]
    }
    result = redact_config(payload)
    assert "auth" not in result["repositories"][0]
    assert result["repositories"][0]["name"] == "r"


def test_password_field_not_redacted() -> None:
    assert redact_config({"password_field": "password"}) == {
        "password_field": "password"
    }


def test_header_dict_sensitive_value_redacted() -> None:
    result = redact_config({"katana_headers": {"Cookie": "c", "User-Agent": "ua"}})
    assert result["katana_headers"]["Cookie"] == REDACTED
    assert result["katana_headers"]["User-Agent"] == "ua"


def test_header_dict_case_insensitive_header_name() -> None:
    result = redact_config({"xsstrike_headers": {"X-API-Key": "k"}})
    assert result["xsstrike_headers"]["X-API-Key"] == REDACTED


def test_url_token_param_redacted() -> None:
    result = redact_config({"url": "https://x.example/login?token=abc&page=2"})
    params = dict(parse_qsl(urlsplit(result["url"]).query))
    assert params["token"] == REDACTED
    assert params["page"] == "2"


def test_url_multiple_blacklist_params_redacted() -> None:
    result = redact_config({"url": "https://x.example/?token=a&password=b&page=3"})
    params = dict(parse_qsl(urlsplit(result["url"]).query))
    assert params["token"] == REDACTED
    assert params["password"] == REDACTED
    assert params["page"] == "3"


def test_url_substring_match() -> None:
    result = redact_config({"url": "https://x.example/?user_token=abc"})
    params = dict(parse_qsl(urlsplit(result["url"]).query))
    assert params["user_token"] == REDACTED


def test_url_without_query_unchanged() -> None:
    url = "https://x.example/path"
    assert redact_config({"url": url}) == {"url": url}


def test_non_url_string_with_token_unchanged() -> None:
    assert redact_config({"note": "token=123"}) == {"note": "token=123"}


def test_list_processed() -> None:
    result = redact_config([{"api_key": "k"}, {"model": "opus"}])
    assert result == [{"api_key": REDACTED}, {"model": "opus"}]


def test_tuple_preserved_as_tuple() -> None:
    result = redact_config(({"api_key": "k"},))
    assert isinstance(result, tuple)
    assert result[0]["api_key"] == REDACTED


def test_immutability() -> None:
    original = {"api_key": "secret", "model": "opus"}
    original_copy = copy.deepcopy(original)
    redact_config(original)
    assert original == original_copy


@pytest.mark.parametrize("value", [None, 42, True])
def test_primitives_pass_through(value: object) -> None:
    assert redact_config(value) is value


def test_redact_exempt_sets_attribute_and_preserves_identity() -> None:
    def handler() -> None: ...

    decorated = redact_exempt(handler)
    assert getattr(decorated, "__redact_exempt__", False) is True
    assert decorated is handler
