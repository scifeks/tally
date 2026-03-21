"""Integration tests for the nmap → ChromaDB ingestion pipeline."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import ProjectManager  # noqa: E402
from application.rag import FindingIngestor, RAGEngine  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.nmap_parser import parse_nmap_xml  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


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
        timestamp=RAGEngine.now_iso(),
        duration_seconds=0.1,
    )


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _write_commands_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/gitleaks",
                },
                "nmap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/nmap",
                },
                "pip-audit": {
                    "type": "repo",
                    "location": "local",
                    "path": "/home/justin/.local/bin/pip-audit",
                },
            }
        )
    )


def _make_rag_engine(project_env: dict) -> RAGEngine:
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        return RAGEngine(
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )


def _get_all_docs(engine: RAGEngine) -> dict[str, list]:
    assert engine._collection is not None
    result = engine._collection.get(include=["documents", "metadatas"])
    return {
        "ids": result["ids"],
        "documents": list(result["documents"] or []),
        "metadatas": list(result["metadatas"] or []),
    }


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


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
    def test_count_host_and_port_chunks(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """1 host + 2 open ports → 3 documents total."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-scan")
        assert len(ingested) == 3
        assert engine.count_documents() == 3

    def test_count_no_open_ports(
        self, project_env: dict, no_ports_parsed_data: dict
    ) -> None:
        """1 host with no open ports → 1 host document, 0 port documents."""
        result = _make_nmap_result(no_ports_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-scan")
        assert len(ingested) == 1
        assert engine.count_documents() == 1

    def test_host_chunk_metadata(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Host chunk metadata fields match expected values."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        host_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" not in m
        ]
        assert len(host_metas) == 1
        meta = host_metas[0]
        assert meta["tool"] == "nmap"
        assert meta["profile"] == "test-scan"
        assert meta["finding_type"] == '["informational"]'
        assert meta["ip_address"] == "127.0.0.1"
        assert meta["source_file"] == ""
        assert "timestamp" in meta

    def test_port_chunk_metadata(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Open port chunk metadata fields, including port as int."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" in m
        ]
        assert len(port_metas) == 2
        port_numbers = {m["port"] for m in port_metas}
        assert port_numbers == {80, 443}
        for meta in port_metas:
            assert meta["tool"] == "nmap"
            assert meta["profile"] == "test-scan"
            assert meta["finding_type"] == '["informational"]'
            assert meta["ip_address"] == "127.0.0.1"
            assert meta["service"] == "http"
            assert isinstance(meta["port"], int)
            assert "timestamp" in meta

    def test_host_text_template_with_hostname(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Host chunk text uses 'ip (hostname)' label and lists open ports."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        host_docs = [
            d
            for d, m in zip(all_docs["documents"], all_docs["metadatas"])
            if m["finding_type"] == '["informational"]' and "port" not in m
        ]
        assert len(host_docs) == 1
        text = host_docs[0]
        assert "[nmap] Host: 127.0.0.1 (localhost)" in text
        assert "Status: up" in text
        assert "80/tcp" in text
        assert "443/tcp" in text

    def test_host_text_template_no_hostname(
        self, project_env: dict, no_ports_parsed_data: dict
    ) -> None:
        """Host chunk text uses bare IP when hostname is empty."""
        result = _make_nmap_result(no_ports_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        text = all_docs["documents"][0]
        assert "[nmap] Host: 192.168.1.1\n" in text
        assert "()" not in text

    def test_host_text_no_open_ports_shows_none(
        self, project_env: dict, no_ports_parsed_data: dict
    ) -> None:
        """Host chunk shows '(none)' when there are no open ports."""
        result = _make_nmap_result(no_ports_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        text = all_docs["documents"][0]
        assert "(none)" in text

    def test_port_text_template(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Open port chunk text matches expected format."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_docs = [
            d
            for d, m in zip(all_docs["documents"], all_docs["metadatas"])
            if m["finding_type"] == '["informational"]' and m.get("port") == 80
        ]
        assert len(port_docs) == 1
        assert "[nmap] Port 80/tcp on 127.0.0.1: http nginx 1.29.5" in port_docs[0]

    def test_no_duplicates(self, project_env: dict, basic_parsed_data: dict) -> None:
        """Ingesting the same data twice does not double the document count."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])
        ingestor.ingest_tool_output(result, profile="test-scan")
        count_after_first = engine.count_documents()
        ingestor.ingest_tool_output(result, profile="test-scan")
        assert engine.count_documents() == count_after_first

    def test_two_profiles_are_independent(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Two profiles coexist; re-ingesting one does not affect the other."""
        engine = _make_rag_engine(project_env)
        ingestor = FindingIngestor(engine, project_env["project_name"])

        result_a = _make_nmap_result(basic_parsed_data)
        ingestor.ingest_tool_output(result_a, profile="profile-a")
        count_a = engine.count_documents()

        result_b = _make_nmap_result(basic_parsed_data)
        ingestor.ingest_tool_output(result_b, profile="profile-b")
        total = engine.count_documents()
        assert total == count_a * 2

        ingestor.ingest_tool_output(result_a, profile="profile-a")
        assert engine.count_documents() == total

    def test_empty_hosts_ingests_nothing(self, project_env: dict) -> None:
        """Parsed data with no hosts produces 0 documents."""
        empty_data = {"scan_info": {}, "hosts": []}
        result = _make_nmap_result(empty_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-scan")
        assert ingested == []
        assert engine.count_documents() == 0

    def test_scripts_fixture_chunk_count(
        self, project_env: dict, scripts_parsed_data: dict
    ) -> None:
        """1 host + 3 open ports = 4 documents."""
        result = _make_nmap_result(scripts_parsed_data)
        engine = _make_rag_engine(project_env)
        ingested = FindingIngestor(
            engine, project_env["project_name"]
        ).ingest_tool_output(result, profile="test-scan")
        assert len(ingested) == 4

    def test_host_chunk_has_hostname_and_state(
        self, project_env: dict, scripts_parsed_data: dict
    ) -> None:
        result = _make_nmap_result(scripts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        host_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" not in m
        ]
        assert len(host_metas) == 1
        meta = host_metas[0]
        assert meta["hostname"] == "testserver.local"
        assert meta["state"] == "up"

    def test_port_chunk_has_transport_and_service_version(
        self, project_env: dict, scripts_parsed_data: dict
    ) -> None:
        result = _make_nmap_result(scripts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" in m
        ]
        for meta in port_metas:
            assert "transport" in meta
            assert "service_version" in meta

    def test_port_chunk_tls_metadata(
        self, project_env: dict, scripts_parsed_data: dict
    ) -> None:
        result = _make_nmap_result(scripts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [m for m in all_docs["metadatas"] if m.get("port") == 443]
        assert len(port_metas) == 1
        meta = port_metas[0]
        assert meta.get("tls") is True
        assert meta.get("tls_version") == "TLSv1.3"

    def test_port_chunk_ssh_algorithms(
        self, project_env: dict, scripts_parsed_data: dict
    ) -> None:
        result = _make_nmap_result(scripts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [m for m in all_docs["metadatas"] if m.get("port") == 22]
        assert len(port_metas) == 1
        assert "ssh_algorithms" in port_metas[0]
        assert len(port_metas[0]["ssh_algorithms"]) > 0

    def test_port_chunk_cve_ids(
        self, project_env: dict, scripts_parsed_data: dict
    ) -> None:
        result = _make_nmap_result(scripts_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [m for m in all_docs["metadatas"] if m.get("port") == 80]
        assert len(port_metas) == 1
        assert "cve_ids" in port_metas[0]
        assert "CVE-2019-9511" in port_metas[0]["cve_ids"]

    def test_optional_fields_absent_when_no_scripts(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" in m
        ]
        for meta in port_metas:
            for key in (
                "tls",
                "tls_version",
                "http_version",
                "ssh_algorithms",
                "cve_ids",
            ):
                assert key not in meta

    def test_host_chunk_shared_metadata(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Host chunks have correct domain/enriched/type_* fields."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        host_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" not in m
        ]
        assert host_metas
        for meta in host_metas:
            assert meta["domain"] == "network"
            assert meta["enriched"] is False
            assert meta["type_exposure"] is False
            assert meta["type_secret"] is False
            assert meta["type_vulnerability"] is False
            assert meta["type_weakness"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_dependency"] is False

    def test_port_chunk_shared_metadata(
        self, project_env: dict, basic_parsed_data: dict
    ) -> None:
        """Open port chunks have correct shared metadata fields."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == '["informational"]' and "port" in m
        ]
        assert port_metas
        for meta in port_metas:
            assert meta["domain"] == "network"
            assert meta["enriched"] is False
            assert meta["type_exposure"] is False
            assert meta["type_secret"] is False
            assert meta["type_vulnerability"] is False
            assert meta["type_weakness"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_dependency"] is False
            assert meta["state"] == "open"
