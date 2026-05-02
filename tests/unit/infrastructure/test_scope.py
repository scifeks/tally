"""Unit tests for infrastructure.tools.wrappers.utils.scope."""

from __future__ import annotations

from infrastructure.tools.wrappers.utils.scope import in_scope, scope_key


class TestScopeKey:
    def test_http_default_port(self) -> None:
        assert scope_key("http://example.com/path") == ("example.com", 80)

    def test_https_default_port(self) -> None:
        assert scope_key("https://example.com/path") == ("example.com", 443)

    def test_explicit_port_preserved(self) -> None:
        assert scope_key("http://example.com:8080/path") == ("example.com", 8080)

    def test_host_is_lowercased(self) -> None:
        assert scope_key("http://EXAMPLE.COM/") == ("example.com", 80)

    def test_localhost(self) -> None:
        assert scope_key("http://localhost:3000/") == ("localhost", 3000)

    def test_ipv4_literal(self) -> None:
        assert scope_key("http://192.168.1.1:8888/foo") == ("192.168.1.1", 8888)

    def test_bare_host_with_port(self) -> None:
        # No scheme; should be treated as http
        assert scope_key("localhost:5000") == ("localhost", 5000)

    def test_unparseable_returns_none(self) -> None:
        assert scope_key("") is None

    def test_no_host_returns_none(self) -> None:
        assert scope_key("http:///path") is None


class TestInScope:
    def test_same_host_same_scheme(self) -> None:
        assert in_scope("http://dvwa.local/login", "http://dvwa.local") is True

    def test_http_vs_https_explicit_same_port_in_scope(self) -> None:
        # Protocol is ignored; only host:port is compared. When the port is
        # explicitly the same, http and https both match.
        assert in_scope("https://dvwa.local:80/login", "http://dvwa.local:80") is True

    def test_different_host_out_of_scope(self) -> None:
        assert (
            in_scope(
                "https://github.com/digininja/DVWA/",
                "http://dvwa.local",
            )
            is False
        )

    def test_same_host_different_port_out_of_scope(self) -> None:
        assert in_scope("http://dvwa.local:8080/", "http://dvwa.local") is False

    def test_localhost_matches(self) -> None:
        assert in_scope("http://localhost:3000/api", "http://localhost:3000") is True

    def test_localhost_port_mismatch(self) -> None:
        assert in_scope("http://localhost:9000/api", "http://localhost:3000") is False

    def test_ipv4_in_scope(self) -> None:
        assert (
            in_scope("http://192.168.1.1:8080/path", "http://192.168.1.1:8080") is True
        )

    def test_unparseable_url_false(self) -> None:
        assert in_scope("", "http://dvwa.local") is False

    def test_unparseable_base_false(self) -> None:
        assert in_scope("http://dvwa.local/", "") is False
