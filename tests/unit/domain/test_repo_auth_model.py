"""Tests for AuthHeader and RepoAuth auth_type validation."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from core.config.schemas.repository import AuthHeader, RepoAuth


class TestAuthHeader:
    def test_inline_value(self) -> None:
        h = AuthHeader(header="Authorization", value="Bearer tok")
        assert h.header == "Authorization"
        assert h.value == "Bearer tok"
        assert h.value_env == ""

    def test_env_var_reference(self) -> None:
        h = AuthHeader(header="X-API-Key", value_env="MY_KEY")
        assert h.value_env == "MY_KEY"
        assert h.value == ""

    def test_header_name_required(self) -> None:
        with pytest.raises(ValidationError):
            AuthHeader(**{"value": "x"})


class TestRepoAuthType:
    def test_defaults_to_form(self) -> None:
        auth = RepoAuth(login_url="http://x.com/login")
        assert auth.auth_type == "form"

    def test_form_requires_login_url(self) -> None:
        with pytest.raises(ValueError, match="login_url"):
            RepoAuth(auth_type="form")

    def test_header_requires_auth_headers(self) -> None:
        with pytest.raises(ValueError, match="auth_headers"):
            RepoAuth(auth_type="header")

    def test_header_auth_valid(self) -> None:
        auth = RepoAuth(
            auth_type="header",
            auth_headers=[
                AuthHeader(header="Authorization", value="Bearer x"),
            ],
        )
        assert auth.auth_type == "header"
        assert len(auth.auth_headers) == 1

    def test_backward_compat_no_auth_type_in_data(self) -> None:
        data: dict[str, Any] = {
            "login_url": "http://x.com/login",
            "username": "admin",
            "password": "pass",
        }
        auth = RepoAuth(**data)
        assert auth.auth_type == "form"
        assert auth.auth_headers == []

    def test_form_auth_serialization_roundtrip(self) -> None:
        auth = RepoAuth(
            login_url="http://x.com/login",
            username="admin",
            password="secret",
        )
        data: dict[str, Any] = auth.model_dump()
        restored = RepoAuth(**data)
        assert restored.login_url == "http://x.com/login"
        assert restored.auth_type == "form"

    def test_header_auth_serialization_roundtrip(self) -> None:
        auth = RepoAuth(
            auth_type="header",
            auth_headers=[
                AuthHeader(header="Authorization", value="Bearer x"),
                AuthHeader(header="X-API-Key", value_env="MY_KEY"),
            ],
        )
        data: dict[str, Any] = auth.model_dump()
        restored = RepoAuth(**data)
        assert restored.auth_type == "header"
        assert len(restored.auth_headers) == 2
        assert restored.auth_headers[0].header == "Authorization"
        assert restored.auth_headers[1].value_env == "MY_KEY"
