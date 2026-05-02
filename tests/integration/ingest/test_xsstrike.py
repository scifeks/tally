"""Integration tests for XSSTrikeHandler.normalize(), render(), fingerprint_key()."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.xsstrike import parse_xsstrike_log  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
_TIMESTAMP = "2024-01-01T00:00:00"
_FIXTURE_LOG = _FIXTURES / "xsstrike_crawl.log"


def _make_result(parsed_data: dict, output_files: dict | None = None) -> ToolResult:
    return ToolResult(
        tool_name="xsstrike",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@pytest.fixture()
def fixture_parsed() -> dict:
    return parse_xsstrike_log(_FIXTURE_LOG)


@pytest.fixture()
def fixture_rows(fixture_parsed: dict) -> list[dict]:
    handler = ToolHandlerFactory.load("xsstrike")
    assert handler is not None
    result = _make_result(fixture_parsed)
    return handler.normalize(result, profile="test-repo")


# ToolHandlerFactory


class TestHandlerLoad:
    def test_handler_registered(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None

    def test_handler_tool_name(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        assert handler.tool_name == "xsstrike"


class TestNormalizeRowCount:
    def test_fixture_produces_two_rows(self, fixture_rows: list[dict]) -> None:
        assert len(fixture_rows) == 2

    def test_empty_findings_produces_no_rows(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        result = _make_result({"findings": [], "summary": {"total_findings": 0}})
        rows = handler.normalize(result, profile="test-repo")
        assert rows == []

    def test_missing_findings_key_produces_no_rows(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        result = _make_result({})
        rows = handler.normalize(result, profile="test-repo")
        assert rows == []

    def test_return_type_is_list_of_dicts(self, fixture_rows: list[dict]) -> None:
        assert isinstance(fixture_rows, list)
        assert all(isinstance(r, dict) for r in fixture_rows)


class TestNormalizeFieldValues:
    def test_tool_field(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["tool"] == "xsstrike"

    def test_profile_field(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["profile"] == "test-repo"

    def test_severity_field(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["severity"] == "high"

    def test_confidence_field(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["confidence"] == "potential"

    def test_cwe_id_is_79(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["cwe_id"] == 79

    def test_risk_type_is_xss(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["risk_type"] == "Cross-Site Scripting (XSS)"

    def test_finding_type_is_vulnerability(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["finding_type"] == json.dumps(["vulnerability"])

    def test_timestamp_propagated(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["timestamp"] == _TIMESTAMP

    def test_urls_from_fixture(self, fixture_rows: list[dict]) -> None:
        urls = {r["url"] for r in fixture_rows}
        assert "https://app.example.com/search" in urls
        assert "https://app.example.com/profile" in urls

    def test_params_from_fixture(self, fixture_rows: list[dict]) -> None:
        by_url = {r["url"]: r for r in fixture_rows}
        assert by_url["https://app.example.com/search"]["param"] == "q"
        assert by_url["https://app.example.com/profile"]["param"] == "name"

    def test_payloads_non_empty(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["payload"], "payload must not be empty"


class TestNormalizeMetadataFlags:
    def test_domain_is_web(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["domain"] == "web"

    def test_type_vulnerability_true(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["type_vulnerability"] is True

    def test_other_type_flags_false(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["type_secret"] is False
            assert row["type_weakness"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_exposure"] is False
            assert row["type_dependency"] is False

    def test_enriched_false(self, fixture_rows: list[dict]) -> None:
        for row in fixture_rows:
            assert row["enriched"] is False


# render()


class TestRender:
    def test_render_contains_url(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        for row in fixture_rows:
            rendered = handler.render(row)
            assert row["url"] in rendered

    def test_render_contains_param(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        for row in fixture_rows:
            rendered = handler.render(row)
            assert row["param"] in rendered

    def test_render_contains_payload(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        for row in fixture_rows:
            rendered = handler.render(row)
            assert row["payload"] in rendered

    def test_render_prefixed_with_xsstrike(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        for row in fixture_rows:
            assert handler.render(row).startswith("[xsstrike]")

    def test_render_contains_cwe(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        for row in fixture_rows:
            assert "79" in handler.render(row)


# fingerprint_key()


class TestFingerprintKey:
    def test_returns_string(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        for row in fixture_rows:
            assert isinstance(handler.fingerprint_key(row), str)

    def test_different_urls_produce_different_keys(
        self, fixture_rows: list[dict]
    ) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        keys = [handler.fingerprint_key(r) for r in fixture_rows]
        assert len(set(keys)) == len(keys), "fingerprint keys must be unique"

    def test_same_finding_same_key(self, fixture_rows: list[dict]) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        row = fixture_rows[0]
        assert handler.fingerprint_key(row) == handler.fingerprint_key(row)

    def test_duplicate_finding_same_key(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        finding = {
            "url": "https://app.example.com/search",
            "param": "q",
            "payload": "<img src=x onerror=alert(1)>",
        }
        key_a = handler.fingerprint_key(finding)
        key_b = handler.fingerprint_key(dict(finding))
        assert key_a == key_b

    def test_different_params_different_keys(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        base = {
            "url": "https://app.example.com/search",
            "payload": "<script>x</script>",
        }
        key_q = handler.fingerprint_key({**base, "param": "q"})
        key_s = handler.fingerprint_key({**base, "param": "search"})
        assert key_q != key_s

    def test_different_payloads_different_keys(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        base = {"url": "https://app.example.com/search", "param": "q"}
        key_a = handler.fingerprint_key({**base, "payload": "<script>a</script>"})
        key_b = handler.fingerprint_key({**base, "payload": "<img src=x>"})
        assert key_a != key_b

    def test_key_format_contains_tool_prefix(self) -> None:
        handler = ToolHandlerFactory.load("xsstrike")
        assert handler is not None
        key = handler.fingerprint_key(
            {
                "url": "https://example.com/",
                "param": "q",
                "payload": "<script>x</script>",
            }
        )
        assert key.startswith("xsstrike|")
