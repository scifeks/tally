"""Auth clear and re-add round-trip through the service helpers."""

from __future__ import annotations

from application.project.repositories_service import (
    _is_auth_cleared,
)


class TestIsAuthCleared:
    def test_header_auth_cleared_by_empty_list(self) -> None:
        merged = {"auth_type": "header", "auth_headers": []}
        patch = {"auth_headers": []}
        assert _is_auth_cleared(merged, patch) is True

    def test_header_auth_not_cleared_when_headers_remain(self) -> None:
        merged = {
            "auth_type": "header",
            "auth_headers": [
                {"header": "Authorization", "value": "x", "value_env": ""}
            ],
        }
        patch = {
            "auth_headers": [{"header": "Authorization", "value": "x", "value_env": ""}]
        }
        assert _is_auth_cleared(merged, patch) is False

    def test_form_auth_cleared_by_empty_login_url(self) -> None:
        merged = {"auth_type": "form", "login_url": ""}
        patch = {"login_url": ""}
        assert _is_auth_cleared(merged, patch) is True

    def test_form_auth_not_cleared_when_url_present(self) -> None:
        merged = {"auth_type": "form", "login_url": "http://x.com/login"}
        patch = {"login_url": "http://x.com/login"}
        assert _is_auth_cleared(merged, patch) is False

    def test_unrelated_patch_does_not_clear(self) -> None:
        merged = {"auth_type": "header", "auth_headers": [], "username": "x"}
        patch = {"username": "x"}
        assert _is_auth_cleared(merged, patch) is False


class TestNoneAuthToHeaderRoundTrip:
    """After clearing auth (auth=None), adding header auth must not fail."""

    def test_header_auth_from_none_constructs_valid_model(self) -> None:
        from core.config.schemas.repository import RepoAuth

        existing_auth: dict[str, object] = {}
        patch = {
            "auth_type": "header",
            "auth_headers": [
                {"header": "X-Foo", "value": "bar", "value_env": ""},
            ],
        }
        merged = {**existing_auth, **patch}
        auth = RepoAuth(**merged)
        assert auth.auth_type == "header"
        assert len(auth.auth_headers) == 1
