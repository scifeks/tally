"""Unit tests for the nmap XML parser (parse_nmap_xml_string, parse_nmap_xml)."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.tools.parsers.nmap_parser import (
    parse_nmap_xml,
    parse_nmap_xml_string,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


def _parse_fixture(filename: str) -> dict:
    return parse_nmap_xml(_FIXTURES / filename)


@pytest.fixture()
def basic_parsed_data() -> dict:
    return _parse_fixture("nmap_basic.xml")


@pytest.fixture()
def no_ports_parsed_data() -> dict:
    return _parse_fixture("nmap_no_open_ports.xml")


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
        for key in (
            "tls",
            "tls_version",
            "http_version",
            "ssh_algorithms",
            "cve_ids",
        ):
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
