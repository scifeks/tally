"""Unit tests for nmap chunk builder metadata (no ChromaDB)."""

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

    def test_host_chunk_severity_informational(self) -> None:
        chunks = self._get_chunks()
        host_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" not in c[1]
        ]
        assert host_chunks, "Expected at least one host chunk"
        assert host_chunks[0][1]["severity"] == "informational"

    def test_open_port_chunk_severity_informational(self) -> None:
        chunks = self._get_chunks()
        port_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" in c[1]
        ]
        assert port_chunks, "Expected at least one open_port chunk"
        assert port_chunks[0][1]["severity"] == "informational"

    def test_host_chunk_no_risk_type(self) -> None:
        chunks = self._get_chunks()
        host_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" not in c[1]
        ]
        assert "risk_type" not in host_chunks[0][1]

    def test_open_port_chunk_no_risk_type(self) -> None:
        chunks = self._get_chunks()
        port_chunks = [
            c
            for c in chunks
            if c[1].get("finding_type") == '["informational"]' and "port" in c[1]
        ]
        assert "risk_type" not in port_chunks[0][1]

    def test_no_type_boolean_true(self) -> None:
        chunks = self._get_chunks()
        for _text, meta, _id in chunks:
            for key, val in meta.items():
                if key.startswith("type_"):
                    assert val is not True, f"{key} should not be True for nmap chunks"
