"""Integration tests for NmapChunkBuilder.normalize() and render()."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.nmap_parser import parse_nmap_xml  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
_TIMESTAMP = "2024-01-01T00:00:00"


def _parse_fixture(filename: str) -> dict:
    return parse_nmap_xml(_FIXTURES / filename)


def _make_nmap_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="nmap",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@pytest.fixture()
def basic_parsed_data() -> dict:
    return _parse_fixture("nmap_basic.xml")


@pytest.fixture()
def no_ports_parsed_data() -> dict:
    return _parse_fixture("nmap_no_open_ports.xml")


@pytest.fixture()
def scripts_parsed_data() -> dict:
    return _parse_fixture("nmap_with_scripts.xml")


class TestNmapIngestor:
    def test_count_host_and_port_chunks(self, basic_parsed_data: dict) -> None:
        """2 open ports → 2 port rows (no host-level rows)."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 2

    def test_count_no_open_ports(self, no_ports_parsed_data: dict) -> None:
        """1 host up with no open ports → 1 host-only row."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(no_ports_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 1

    def test_host_chunk_metadata(self, basic_parsed_data: dict) -> None:
        """Port rows include ip_address, profile, tool, and finding_type."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 2
        for row in rows:
            assert row["tool"] == "nmap"
            assert row["profile"] == "test-scan"
            assert row["finding_type"] == '["exposure"]'
            assert row["ip_address"] == "127.0.0.1"
            assert row["source_file"] == ""
            assert "timestamp" in row

    def test_port_chunk_metadata(self, basic_parsed_data: dict) -> None:
        """Open port rows include port number as int."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 2
        port_numbers = {row["port"] for row in rows}
        assert port_numbers == {80, 443}
        for row in rows:
            assert row["tool"] == "nmap"
            assert row["profile"] == "test-scan"
            assert row["finding_type"] == '["exposure"]'
            assert row["ip_address"] == "127.0.0.1"
            assert row["service"] == "http"
            assert isinstance(row["port"], int)
            assert "timestamp" in row

    def test_host_text_template_with_hostname(self, basic_parsed_data: dict) -> None:
        """Rendered text includes ip, port, and state."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 2
        for row in rows:
            text = handler.render(row)
            assert "[nmap] Host: 127.0.0.1" in text
            assert "Port:" in text
            assert "State: open" in text

    def test_host_text_template_no_hostname(self, no_ports_parsed_data: dict) -> None:
        """Host up with no open ports → 1 row, render shows 'up (no open ports)'."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(no_ports_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 1
        text = handler.render(rows[0])
        assert "[nmap] Host:" in text
        assert "up (no open ports)" in text

    def test_host_text_no_open_ports_shows_none(
        self, no_ports_parsed_data: dict
    ) -> None:
        """Host up with no open ports → 1 host-only row, no port field."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(no_ports_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 1
        assert "port" not in rows[0]

    def test_port_text_template(self, basic_parsed_data: dict) -> None:
        """Port row render matches expected format."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        port_80_rows = [r for r in rows if r.get("port") == 80]
        assert len(port_80_rows) == 1
        text = handler.render(port_80_rows[0])
        assert (
            "[nmap] Host: 127.0.0.1 | Port: 80/tcp | Service: http | State: open"
            in text
        )

    def test_no_duplicates(self, basic_parsed_data: dict) -> None:
        """normalize() is deterministic — same input produces same count."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows_first = handler.normalize(result, profile="test-scan")
        rows_second = handler.normalize(result, profile="test-scan")
        assert len(rows_first) == len(rows_second)

    def test_two_profiles_are_independent(self, basic_parsed_data: dict) -> None:
        """normalize() sets the profile field correctly per call."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows_a = handler.normalize(result, profile="profile-a")
        rows_b = handler.normalize(result, profile="profile-b")
        assert all(r["profile"] == "profile-a" for r in rows_a)
        assert all(r["profile"] == "profile-b" for r in rows_b)

    def test_empty_hosts_ingests_nothing(self) -> None:
        """Parsed data with no hosts → 0 rows."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        empty_data: dict = {"scan_info": {}, "hosts": []}
        result = _make_nmap_result(empty_data)
        rows = handler.normalize(result, profile="test-scan")
        assert rows == []

    def test_scripts_fixture_chunk_count(self, scripts_parsed_data: dict) -> None:
        """3 open ports → 3 rows (no host-level row)."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(scripts_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 3

    def test_host_chunk_has_hostname_and_state(self, scripts_parsed_data: dict) -> None:
        """Port rows include ip_address and state."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(scripts_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert len(rows) == 3
        for row in rows:
            assert row["state"] == "open"
            assert row["ip_address"]

    def test_port_chunk_has_transport_and_service_version(
        self, scripts_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(scripts_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        for row in rows:
            assert "transport" in row
            assert "service_version" in row

    def test_port_chunk_tls_metadata(self, scripts_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(scripts_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        port_443_rows = [r for r in rows if r.get("port") == 443]
        assert len(port_443_rows) == 1
        row = port_443_rows[0]
        assert row.get("tls") is True
        assert row.get("tls_version") == "TLSv1.3"

    def test_port_chunk_ssh_algorithms(self, scripts_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(scripts_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        port_22_rows = [r for r in rows if r.get("port") == 22]
        assert len(port_22_rows) == 1
        assert "ssh_algorithms" in port_22_rows[0]
        assert len(port_22_rows[0]["ssh_algorithms"]) > 0

    def test_port_chunk_cve_ids(self, scripts_parsed_data: dict) -> None:
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(scripts_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        port_80_rows = [r for r in rows if r.get("port") == 80]
        assert len(port_80_rows) == 1
        assert "cve_ids" in port_80_rows[0]
        assert "CVE-2019-9511" in port_80_rows[0]["cve_ids"]

    def test_optional_fields_absent_when_no_scripts(
        self, basic_parsed_data: dict
    ) -> None:
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        for row in rows:
            for key in (
                "tls",
                "tls_version",
                "http_version",
                "ssh_algorithms",
                "cve_ids",
            ):
                assert key not in row

    def test_host_chunk_shared_metadata(self, basic_parsed_data: dict) -> None:
        """Port rows have correct domain/enriched/type_* fields."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert rows
        for row in rows:
            assert row["domain"] == "network"
            assert row["enriched"] is False
            assert row["type_exposure"] is True
            assert row["type_informational"] is False
            assert row["type_secret"] is False
            assert row["type_vulnerability"] is False
            assert row["type_weakness"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_dependency"] is False

    def test_port_chunk_shared_metadata(self, basic_parsed_data: dict) -> None:
        """Open port rows have correct shared metadata fields."""
        handler = ToolHandlerFactory.load("nmap")
        assert handler is not None
        result = _make_nmap_result(basic_parsed_data)
        rows = handler.normalize(result, profile="test-scan")
        assert rows
        for row in rows:
            assert row["domain"] == "network"
            assert row["enriched"] is False
            assert row["type_exposure"] is True
            assert row["type_informational"] is False
            assert row["type_secret"] is False
            assert row["type_vulnerability"] is False
            assert row["type_weakness"] is False
            assert row["type_misconfiguration"] is False
            assert row["type_dependency"] is False
            assert row["state"] == "open"
