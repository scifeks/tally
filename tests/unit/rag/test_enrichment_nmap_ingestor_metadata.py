"""Unit tests for nmap handler metadata (no ChromaDB)."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.rag.ingestor import FindingIngestor
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

    def _get_chunks(self):
        ingestor = FindingIngestor(MagicMock(), "test-proj")
        return ingestor._build_chunks(self._make_nmap_result(), "default")

    def test_no_host_level_chunks(self) -> None:
        chunks = self._get_chunks()
        host_chunks = [c for c in chunks if "port" not in c[1]]
        assert host_chunks == [], "Host-level chunks must not be produced"

    def test_one_chunk_per_open_port(self) -> None:
        chunks = self._get_chunks()
        assert len(chunks) == 1

    def test_port_chunk_finding_type_exposure(self) -> None:
        chunks = self._get_chunks()
        assert chunks[0][1]["finding_type"] == '["exposure"]'

    def test_port_chunk_type_exposure_true(self) -> None:
        chunks = self._get_chunks()
        assert chunks[0][1]["type_exposure"] is True

    def test_port_chunk_severity_informational(self) -> None:
        chunks = self._get_chunks()
        assert chunks[0][1]["severity"] == "informational"

    def test_port_chunk_no_risk_type(self) -> None:
        chunks = self._get_chunks()
        assert "risk_type" not in chunks[0][1]
