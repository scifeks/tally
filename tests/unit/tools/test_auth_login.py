"""Unit tests for infrastructure.tools.wrappers.utils.auth_login."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.tools.wrappers.utils.auth_login import (
    _HiddenInputParser,
    _resolve_credentials,
    perform_login,
)


def _make_auth(
    *,
    credentials_env: str = "",
    username: str = "",
    password: str = "",
    login_url: str = "http://example.com/login",
    username_field: str = "username",
    password_field: str = "password",
    extra_fields: dict | None = None,
) -> MagicMock:
    auth = MagicMock()
    auth.credentials_env = credentials_env
    auth.username = username
    auth.password = password
    auth.login_url = login_url
    auth.username_field = username_field
    auth.password_field = password_field
    auth.extra_fields = extra_fields or {}
    return auth


# _HiddenInputParser


class TestHiddenInputParser:
    def test_extracts_single_hidden_field(self) -> None:
        parser = _HiddenInputParser()
        parser.feed('<input type="hidden" name="csrf" value="abc123">')
        assert parser.hidden == {"csrf": "abc123"}

    def test_extracts_multiple_hidden_fields(self) -> None:
        parser = _HiddenInputParser()
        parser.feed(
            '<input type="hidden" name="token" value="x">'
            '<input type="hidden" name="_method" value="POST">'
        )
        assert parser.hidden == {"token": "x", "_method": "POST"}

    def test_ignores_non_hidden_inputs(self) -> None:
        parser = _HiddenInputParser()
        parser.feed(
            '<input type="text" name="username" value="admin">'
            '<input type="hidden" name="csrf" value="tok">'
        )
        assert parser.hidden == {"csrf": "tok"}

    def test_handles_none_type_attribute(self) -> None:
        parser = _HiddenInputParser()
        parser.handle_starttag("input", [("type", None), ("name", "x"), ("value", "y")])
        assert parser.hidden == {}

    def test_handles_uppercase_type(self) -> None:
        parser = _HiddenInputParser()
        parser.feed('<input TYPE="HIDDEN" name="tok" value="v">')
        assert parser.hidden == {"tok": "v"}

    def test_field_with_empty_value(self) -> None:
        parser = _HiddenInputParser()
        parser.feed('<input type="hidden" name="empty_field" value="">')
        assert parser.hidden == {"empty_field": ""}

    def test_field_with_no_value_attribute(self) -> None:
        parser = _HiddenInputParser()
        parser.feed('<input type="hidden" name="novalue">')
        assert parser.hidden == {"novalue": ""}

    def test_skips_hidden_field_without_name(self) -> None:
        parser = _HiddenInputParser()
        parser.feed('<input type="hidden" value="orphan">')
        assert parser.hidden == {}

    def test_empty_html_yields_empty_dict(self) -> None:
        parser = _HiddenInputParser()
        parser.feed("<html><body><form></form></body></html>")
        assert parser.hidden == {}


# _resolve_credentials


class TestResolveCredentials:
    def test_env_var_takes_precedence_over_inline(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_CREDS", "envuser:envpass")
        auth = _make_auth(
            credentials_env="MY_CREDS",
            username="inlineuser",
            password="inlinepass",
        )
        result = _resolve_credentials(auth)
        assert result == ("envuser", "envpass")

    def test_env_var_with_colon_in_password(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_CREDS", "user:p:ass:word")
        auth = _make_auth(credentials_env="MY_CREDS")
        result = _resolve_credentials(auth)
        assert result == ("user", "p:ass:word")

    def test_inline_fallback_when_env_var_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("MY_CREDS", raising=False)
        auth = _make_auth(
            credentials_env="MY_CREDS",
            username="fallback_user",
            password="fallback_pass",
        )
        result = _resolve_credentials(auth)
        assert result == ("fallback_user", "fallback_pass")

    def test_inline_used_when_no_credentials_env_set(self) -> None:
        auth = _make_auth(username="direct_user", password="direct_pass")
        result = _resolve_credentials(auth)
        assert result == ("direct_user", "direct_pass")

    def test_returns_none_when_env_var_missing_colon(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_CREDS", "usernocolon")
        auth = _make_auth(credentials_env="MY_CREDS")
        result = _resolve_credentials(auth)
        assert result is None

    def test_returns_none_when_no_credentials_at_all(self) -> None:
        auth = _make_auth()
        result = _resolve_credentials(auth)
        assert result is None

    def test_env_var_empty_string_falls_back_to_inline(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_CREDS", "")
        auth = _make_auth(
            credentials_env="MY_CREDS",
            username="inline_u",
            password="inline_p",
        )
        result = _resolve_credentials(auth)
        assert result == ("inline_u", "inline_p")


# perform_login


class TestPerformLogin:
    def _make_ctx_manager(
        self,
        *,
        get_html: str = "",
        get_cookies: dict | None = None,
        post_status: int = 302,
        jar_items: list[tuple[str, str]] | None = None,
    ) -> MagicMock:
        """Return a mock context manager whose __enter__ yields a client mock."""
        get_resp = MagicMock()
        get_resp.text = get_html
        get_resp.cookies = get_cookies or {}

        post_resp = MagicMock()
        post_resp.status_code = post_status

        items = jar_items or []
        mock_jar = MagicMock()
        mock_jar.__bool__ = MagicMock(return_value=bool(items))
        mock_jar.items.return_value = items

        client = MagicMock()
        client.get.return_value = get_resp
        client.post.return_value = post_resp
        client.cookies = mock_jar

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=client)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    def test_returns_cookie_header_on_success(self) -> None:
        auth = _make_auth(username="admin", password="secret")
        ctx = self._make_ctx_manager(
            jar_items=[("session", "abc"), ("PHPSESSID", "xyz")],
        )
        with patch("httpx.Client", return_value=ctx):
            result = perform_login(auth)

        assert result == {"Cookie": "session=abc; PHPSESSID=xyz"}

    def test_hidden_csrf_token_included_in_post(self) -> None:
        auth = _make_auth(username="u", password="p")
        html = '<input type="hidden" name="user_token" value="tok123">'
        ctx = self._make_ctx_manager(
            get_html=html,
            jar_items=[("PHPSESSID", "sess")],
        )
        with patch("httpx.Client", return_value=ctx):
            perform_login(auth)

        client = ctx.__enter__.return_value
        _, call_kwargs = client.post.call_args
        payload = call_kwargs.get("data", {})
        assert payload.get("user_token") == "tok123"
        assert payload.get("username") == "u"
        assert payload.get("password") == "p"

    def test_extra_fields_included_in_post_payload(self) -> None:
        auth = _make_auth(
            username="admin",
            password="pass",
            extra_fields={"Login": "Login"},
        )
        ctx = self._make_ctx_manager(jar_items=[("PHPSESSID", "sess")])
        with patch("httpx.Client", return_value=ctx):
            perform_login(auth)

        client = ctx.__enter__.return_value
        _, call_kwargs = client.post.call_args
        payload = call_kwargs.get("data", {})
        assert payload.get("Login") == "Login"

    def test_returns_empty_dict_when_no_credentials(self) -> None:
        auth = _make_auth()
        result = perform_login(auth)
        assert result == {}

    def test_returns_empty_dict_when_no_cookies_set(self) -> None:
        auth = _make_auth(username="u", password="p")
        ctx = self._make_ctx_manager(jar_items=[])
        with patch("httpx.Client", return_value=ctx):
            result = perform_login(auth)

        assert result == {}

    def test_returns_empty_dict_on_network_error(self) -> None:
        auth = _make_auth(username="u", password="p")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(side_effect=Exception("connection refused"))
        ctx.__exit__ = MagicMock(return_value=False)
        with patch("httpx.Client", return_value=ctx):
            result = perform_login(auth)

        assert result == {}

    def test_cookies_merged_as_semicolon_separated_string(self) -> None:
        auth = _make_auth(username="a", password="b")
        ctx = self._make_ctx_manager(
            jar_items=[("a", "1"), ("b", "2"), ("c", "3")],
        )
        with patch("httpx.Client", return_value=ctx):
            result = perform_login(auth)

        assert result == {"Cookie": "a=1; b=2; c=3"}
