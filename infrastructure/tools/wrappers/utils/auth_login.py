"""Pre-crawl form login helper.

Performs a GET then POST login sequence against a form-based login page,
extracts the session cookie from the response, and returns a ``Cookie:``
header dict ready to be merged into Katana's ``-H`` arguments.

Credential resolution order
---------------------------
1. If ``auth.credentials_env`` is set and the env var exists, parse it as
   ``user:pass`` (first colon is the delimiter).
2. Otherwise fall back to inline ``auth.username`` / ``auth.password``.
3. If neither is available, return ``{}`` and log a warning.
"""

from __future__ import annotations

import logging
import os
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from core.config.schemas.repository import AuthHeader

if TYPE_CHECKING:
    from core.config.schemas.repository import RepoAuth

logger = logging.getLogger(__name__)


class _HiddenInputParser(HTMLParser):
    """Collect name/value pairs from <input type="hidden"> elements."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "input":
            return
        kv = dict(attrs)
        if (kv.get("type") or "").lower() == "hidden":
            name = kv.get("name")
            value = kv.get("value", "") or ""
            if name:
                self.hidden[name] = value


def _resolve_credentials(auth: RepoAuth) -> tuple[str, str] | None:
    """Return (username, password) or None if credentials are unavailable."""
    if auth.credentials_env:
        raw = os.environ.get(auth.credentials_env, "")
        if raw:
            first_colon = raw.find(":")
            if first_colon > 0:
                return raw[:first_colon], raw[first_colon + 1 :]
            logger.warning(
                "auth.credentials_env %r does not contain a colon separator",
                auth.credentials_env,
            )
    if auth.username and auth.password:
        return auth.username, auth.password
    logger.warning(
        "No credentials found for auth.login_url=%r; "
        "set credentials_env or inline username/password. "
        "Katana will crawl without authentication.",
        auth.login_url,
    )
    return None


def perform_login(auth: RepoAuth) -> dict[str, str]:
    """Login to *auth.login_url* and return a ``{\"Cookie\": \"...\"}`` dict.

    Returns an empty dict when credentials are unavailable or login fails.
    """
    import httpx

    creds = _resolve_credentials(auth)
    if creds is None:
        return {}

    username, password = creds

    try:
        with httpx.Client(
            follow_redirects=True, timeout=15, verify=auth.verify_ssl
        ) as client:
            # GET first to harvest CSRF tokens from hidden inputs
            get_resp = client.get(auth.login_url)
            get_resp.raise_for_status()

            parser = _HiddenInputParser()
            parser.feed(get_resp.text)
            hidden = parser.hidden

            payload: dict[str, str] = {
                **hidden,
                auth.username_field: username,
                auth.password_field: password,
                **auth.extra_fields,
            }

            post_resp = client.post(
                auth.login_url,
                data=payload,
                cookies=get_resp.cookies,
            )
            post_resp.raise_for_status()

            # Cookies may be set at any point in the redirect chain
            jar = client.cookies
            if not jar:
                logger.warning(
                    "Login to %r succeeded (HTTP %d) but no cookies were set.",
                    auth.login_url,
                    post_resp.status_code,
                )
                return {}

            cookie_str = "; ".join(f"{k}={v}" for k, v in jar.items())
            logger.info(
                "Login to %r succeeded; injecting %d cookie(s) into Katana",
                auth.login_url,
                len(jar),
            )
            return {"Cookie": cookie_str}

    except Exception as exc:
        logger.warning(
            "Pre-crawl login to %r failed: %s; Katana will crawl without auth",
            auth.login_url,
            exc,
        )
        return {}


def resolve_auth_headers(
    auth: RepoAuth | None,
) -> dict[str, str]:
    """Resolve header-based auth into a header dict.

    Returns an empty dict for None or form auth.
    """
    if auth is None or auth.auth_type != "header":
        return {}
    headers: dict[str, str] = {}
    for entry in auth.auth_headers:
        value = _resolve_header_value(entry)
        if value:
            headers[entry.header] = value
    return headers


def _resolve_header_value(entry: AuthHeader) -> str:
    """Resolve a single auth header entry's value."""
    if entry.value_env:
        raw = os.environ.get(entry.value_env, "")
        if raw:
            return raw
        logger.warning(
            "Auth header %r references env var %r "
            "which is not set; falling back to inline value",
            entry.header,
            entry.value_env,
        )
    return entry.value


def build_tool_headers(
    auth: RepoAuth | None,
    tool_headers: dict[str, str] | None,
) -> dict[str, str]:
    """Merge resolved auth headers with tool-specific headers.

    Tool-specific headers take precedence on key conflicts.
    """
    safe = tool_headers or {}
    resolved = resolve_auth_headers(auth)
    if not resolved:
        return dict(safe)
    return {**resolved, **safe}
