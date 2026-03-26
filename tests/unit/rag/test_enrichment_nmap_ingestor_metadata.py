"""Unit tests for NmapHandler.normalize() metadata."""

from __future__ import annotations

from application.rag.chunks.nmap import NmapHandler
from domain.tools.base import ToolResult


class TestNmapIngestorMetadata:
    def _make_nmap_result(self) -> ToolResult:
        return ToolResult(
            tool_name="nmap",
            success=True,
            output="",
            parsed_data={
                "hosts": [
                    {
                        "ip_address": "10.0.0.1",
                        "hostname": "target.local",
                        "state": "up",
                        "ports": [
                            {
                                "port": 22,
                                "transport": "tcp",
                                "state": "open",
                                "service": "ssh",
                                "service_version": "",
                            }
                        ],
                    }
                ]
            },
            output_files={},
            timestamp="2024-01-01T00:00:00",
            duration_seconds=0.1,
        )

    def _get_rows(self) -> list[dict]:
        return NmapHandler().normalize(self._make_nmap_result(), "default")

    def test_no_host_level_rows(self) -> None:
        rows = self._get_rows()
        host_rows = [r for r in rows if "port" not in r]
        assert host_rows == [], "Host-level rows must not be produced"

    def test_one_row_per_open_port(self) -> None:
        rows = self._get_rows()
        assert len(rows) == 1

    def test_port_row_finding_type_exposure(self) -> None:
        rows = self._get_rows()
        assert rows[0]["finding_type"] == '["exposure"]'

    def test_port_row_type_exposure_true(self) -> None:
        rows = self._get_rows()
        assert rows[0]["type_exposure"] is True

    def test_port_row_severity_informational(self) -> None:
        rows = self._get_rows()
        assert rows[0]["severity"] == "informational"

    def test_port_row_no_risk_type(self) -> None:
        rows = self._get_rows()
        assert "risk_type" not in rows[0]
