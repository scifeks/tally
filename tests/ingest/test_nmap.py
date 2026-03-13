"""Integration tests for the nmap → ChromaDB ingestion pipeline.

Run from the tally project root:
    pytest tests/ingest/test_nmap.py -v
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.project import ProjectManager  # noqa: E402
from core.rag import FindingIngestor, RAGEngine  # noqa: E402
from core.tools.base import ToolResult  # noqa: E402
from core.tools.parsers.nmap_parser import (  # noqa: E402
    parse_nmap_xml,
    parse_nmap_xml_string,
)

_OLLAMA_URL = "http://localhost:11434"
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ingest"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama_base_url": _OLLAMA_URL,
                "default_llm": "qwen3:14b",
                "default_embedding": "nomic-embed-text:latest",
            }
        )
    )


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm._create_project_dirs(name)
    pm._save_project(name, [])
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


# ---------------------------------------------------------------------------
# Parser unit tests  (no binary, no Ollama, no ChromaDB)
# ---------------------------------------------------------------------------


class TestNmapParser:
    def test_parse_xml_string_basic(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun args="nmap -sV localhost" startstr="2026">
          <host>
            <status state="up"/>
            <address addr="10.0.0.1" addrtype="ipv4"/>
            <hostnames><hostname name="myhost" type="user"/></hostnames>
            <ports>
              <port protocol="tcp" portid="22">
                <state state="open"/>
                <service name="ssh" product="OpenSSH" version="8.9"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        parsed = parse_nmap_xml_string(xml)
        assert "hosts" in parsed
        assert len(parsed["hosts"]) == 1
        host = parsed["hosts"][0]
        assert host["ip_address"] == "10.0.0.1"
        assert host["hostname"] == "myhost"
        assert host["state"] == "up"
        assert len(host["ports"]) == 1
        port = host["ports"][0]
        assert port["port"] == 22
        assert port["transport"] == "tcp"
        assert port["state"] == "open"
        assert port["service"] == "ssh"

    def test_parse_error_returns_error_key(self) -> None:
        result = parse_nmap_xml_string("this is not xml <<<")
        assert "error" in result

    def test_version_combines_product_and_version(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http" product="nginx" version="1.29.5"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        parsed = parse_nmap_xml_string(xml)
        port = parsed["hosts"][0]["ports"][0]
        assert port["service_version"] == "nginx 1.29.5"

    def test_version_empty_when_no_service_element(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="9999">
                <state state="open"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        parsed = parse_nmap_xml_string(xml)
        port = parsed["hosts"][0]["ports"][0]
        assert port["service_version"] == ""
        assert port["service"] == ""

    def test_hostname_falls_back_to_empty(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports/>
          </host>
        </nmaprun>"""
        parsed = parse_nmap_xml_string(xml)
        assert parsed["hosts"][0]["hostname"] == ""

    def test_unknown_scripts_not_in_port_keys(self) -> None:
        """Unknown <script> elements do not add extra keys to the port dict."""
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http" product="nginx" version="1.29.5"/>
                <script id="http-csrf" output="Found CSRF"/>
                <script id="http-dombased-xss" output="Found XSS"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        parsed = parse_nmap_xml_string(xml)
        port = parsed["hosts"][0]["ports"][0]
        assert set(port.keys()) == {
            "port",
            "transport",
            "state",
            "service",
            "service_version",
        }

    def test_ssl_enum_ciphers_sets_tls_fields(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="443">
                <state state="open"/>
                <service name="https" product="nginx" version="1.29.5"/>
                <script id="ssl-enum-ciphers" output="...">
                  <table key="TLSv1.2"><table key="ciphers"/></table>
                  <table key="TLSv1.3"><table key="ciphers"/></table>
                </script>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        assert port.get("tls") is True
        assert port.get("tls_version") == "TLSv1.3"

    def test_tls_version_highest_wins(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="443">
                <state state="open"/>
                <service name="https"/>
                <script id="ssl-enum-ciphers" output="...">
                  <table key="TLSv1.0"/>
                  <table key="TLSv1.2"/>
                </script>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        assert port.get("tls_version") == "TLSv1.2"

    def test_ssh_algorithms_extracted(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="22">
                <state state="open"/>
                <service name="ssh" product="OpenSSH" version="8.9p1"/>
                <script id="ssh2-enum-algos" output="...">
                  <table key="kex_algorithms">
                    <elem>curve25519-sha256</elem>
                    <elem>diffie-hellman-group14-sha256</elem>
                  </table>
                  <table key="encryption_algorithms">
                    <elem>aes128-ctr</elem>
                  </table>
                </script>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        assert "ssh_algorithms" in port
        assert len(port["ssh_algorithms"]) > 0

    def test_vulners_cve_ids_extracted(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http" product="nginx" version="1.29.5"/>
                <script id="vulners" output="...">
                  <table>
                    <elem key="id">CVE-2019-9511</elem>
                    <elem key="cvss">7.5</elem>
                  </table>
                  <table>
                    <elem key="id">CVE-2019-9513</elem>
                    <elem key="cvss">7.5</elem>
                  </table>
                </script>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        assert port.get("cve_ids") == "CVE-2019-9511,CVE-2019-9513"

    def test_http2_via_service_name(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="443">
                <state state="open"/>
                <service name="http2" product="nginx" version="1.29.5"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        assert port.get("http_version") == "http/2"

    def test_http_methods_sets_http_version(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http" product="nginx" version="1.29.5"/>
                <script id="http-methods" output="GET HEAD POST OPTIONS"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        assert port.get("http_version") == "http/1.1"

    def test_no_scripts_omits_optional_fields(self) -> None:
        xml = """<?xml version="1.0"?>
        <nmaprun>
          <host>
            <status state="up"/>
            <address addr="1.2.3.4" addrtype="ipv4"/>
            <hostnames/>
            <ports>
              <port protocol="tcp" portid="80">
                <state state="open"/>
                <service name="http" product="nginx" version="1.29.5"/>
              </port>
            </ports>
          </host>
        </nmaprun>"""
        port = parse_nmap_xml_string(xml)["hosts"][0]["ports"][0]
        for key in ("tls", "tls_version", "http_version", "ssh_algorithms", "cve_ids"):
            assert key not in port.keys()

    def test_basic_fixture_host_count(self, basic_parsed_data: dict) -> None:
        assert len(basic_parsed_data["hosts"]) == 1

    def test_basic_fixture_open_port_count(self, basic_parsed_data: dict) -> None:
        host = basic_parsed_data["hosts"][0]
        open_ports = [p for p in host["ports"] if p["state"] == "open"]
        assert len(open_ports) == 2

    def test_no_ports_fixture_no_open_ports(self, no_ports_parsed_data: dict) -> None:
        host = no_ports_parsed_data["hosts"][0]
        open_ports = [p for p in host["ports"] if p["state"] == "open"]
        assert len(open_ports) == 0


# ---------------------------------------------------------------------------
# Ingestor unit tests
# ---------------------------------------------------------------------------


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
            if m["finding_type"] == "informational" and "port" not in m
        ]
        assert len(host_metas) == 1
        meta = host_metas[0]
        assert meta["tool"] == "nmap"
        assert meta["profile"] == "test-scan"
        assert meta["finding_type"] == "informational"
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
            if m["finding_type"] == "informational" and "port" in m
        ]
        assert len(port_metas) == 2
        port_numbers = {m["port"] for m in port_metas}
        assert port_numbers == {80, 443}
        for meta in port_metas:
            assert meta["tool"] == "nmap"
            assert meta["profile"] == "test-scan"
            assert meta["finding_type"] == "informational"
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
            if m["finding_type"] == "informational" and "port" not in m
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
            if m["finding_type"] == "informational" and m.get("port") == 80
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
            if m["finding_type"] == "informational" and "port" not in m
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
            if m["finding_type"] == "informational" and "port" in m
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
            if m["finding_type"] == "informational" and "port" in m
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
        """Host chunks have correct domain/tool_type/enriched/type_* fields."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        host_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == "informational" and "port" not in m
        ]
        assert host_metas
        for meta in host_metas:
            assert meta["domain"] == "network"
            assert meta["tool_type"] == "network"
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
        """Open port chunks have correct shared metadata fields and state='open'."""
        result = _make_nmap_result(basic_parsed_data)
        engine = _make_rag_engine(project_env)
        FindingIngestor(engine, project_env["project_name"]).ingest_tool_output(
            result, profile="test-scan"
        )
        all_docs = _get_all_docs(engine)
        port_metas = [
            m
            for m in all_docs["metadatas"]
            if m["finding_type"] == "informational" and "port" in m
        ]
        assert port_metas
        for meta in port_metas:
            assert meta["domain"] == "network"
            assert meta["tool_type"] == "network"
            assert meta["enriched"] is False
            assert meta["type_exposure"] is False
            assert meta["type_secret"] is False
            assert meta["type_vulnerability"] is False
            assert meta["type_weakness"] is False
            assert meta["type_misconfiguration"] is False
            assert meta["type_dependency"] is False
            assert meta["state"] == "open"
