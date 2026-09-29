"""Unit tests for BurpToolWrapper properties."""

from __future__ import annotations

from unittest.mock import patch

from domain.tools.interface import TransportType
from infrastructure.tools.wrappers.burp import BurpToolWrapper


class TestBurpToolWrapperProperties:
    def _make_wrapper(self) -> BurpToolWrapper:
        from core.config.schemas.burp_config import BurpConfig

        return BurpToolWrapper(
            burp_config=BurpConfig(base_url="http://localhost:1337"),
        )

    def test_name(self) -> None:
        assert self._make_wrapper().name == "burp"

    def test_scan_segment(self) -> None:
        assert self._make_wrapper().scan_segment == "web"

    def test_transport_is_http(self) -> None:
        assert self._make_wrapper().transport == TransportType.HTTP

    def test_category(self) -> None:
        assert self._make_wrapper().category == "web"

    def test_scope(self) -> None:
        assert self._make_wrapper().scope == "repository"

    def test_skip_is_false(self) -> None:
        assert self._make_wrapper().skip is False

    def test_should_visualize(self) -> None:
        assert self._make_wrapper().should_visualize is True

    def test_requires_base_urls(self) -> None:
        assert self._make_wrapper().requires_base_urls is True

    def test_always_run(self) -> None:
        assert self._make_wrapper().always_run is True

    def test_language_gates_empty(self) -> None:
        assert self._make_wrapper().language_gates == []

    def test_candidate_commands_empty(self) -> None:
        assert self._make_wrapper().candidate_commands == []

    def test_findings_exit_ok(self) -> None:
        assert self._make_wrapper().findings_exit_ok is True

    def test_count_findings(self) -> None:
        wrapper = self._make_wrapper()
        parsed = {"summary": {"total_findings": 7}}
        assert wrapper.count_findings(parsed) == 7

    def test_count_findings_empty(self) -> None:
        wrapper = self._make_wrapper()
        assert wrapper.count_findings({}) == 0

    def test_check_available_delegates_to_probe(self) -> None:
        wrapper = self._make_wrapper()
        with patch(
            "infrastructure.tools.wrappers.burp.probe_burp_availability",
            return_value=True,
        ):
            assert wrapper.check_available() is True

    def test_check_available_false_when_offline(self) -> None:
        wrapper = self._make_wrapper()
        with patch(
            "infrastructure.tools.wrappers.burp.probe_burp_availability",
            return_value=False,
        ):
            assert wrapper.check_available() is False

    def test_check_available_false_when_none(self) -> None:
        wrapper = self._make_wrapper()
        with patch(
            "infrastructure.tools.wrappers.burp.probe_burp_availability",
            return_value=None,
        ):
            assert wrapper.check_available() is False
