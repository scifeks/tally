import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_TLS_VERSION_RANK = {"SSLv3": 0, "TLSv1.0": 1, "TLSv1.1": 2, "TLSv1.2": 3, "TLSv1.3": 4}


def parse_nmap_xml(xml_path: Path) -> dict[str, Any]:
    """Parse an nmap XML output file into structured data."""
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
    except ET.ParseError as exc:
        return {"error": f"XML parse error: {exc}"}
    return _parse_nmaprun(root)


def parse_nmap_xml_string(xml_string: str) -> dict[str, Any]:
    """Parse nmap XML from a raw string into structured data."""
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as exc:
        return {"error": f"XML parse error: {exc}", "raw_output": xml_string}
    return _parse_nmaprun(root)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_nmaprun(root: ET.Element) -> dict[str, Any]:
    scan_info: dict[str, Any] = {
        "version": root.get("version", ""),
        "args": root.get("args", ""),
        "start_time": root.get("startstr", ""),
    }
    hosts = [_parse_host(h) for h in root.findall("host")]
    return {"scan_info": scan_info, "hosts": hosts}


def _parse_host(host_el: ET.Element) -> dict[str, Any]:
    status_el = host_el.find("status")
    state = status_el.get("state", "unknown") if status_el is not None else "unknown"

    ip_address = ""
    for addr_el in host_el.findall("address"):
        if addr_el.get("addrtype") in ("ipv4", "ipv6"):
            ip_address = addr_el.get("addr", "")
            break

    hostname = ""
    hostnames_el = host_el.find("hostnames")
    if hostnames_el is not None:
        first = hostnames_el.find("hostname")
        if first is not None:
            hostname = first.get("name", "")

    ports: list[dict[str, Any]] = []
    ports_el = host_el.find("ports")
    if ports_el is not None:
        for port_el in ports_el.findall("port"):
            ports.append(_parse_port(port_el))

    return {
        "ip_address": ip_address,
        "hostname": hostname,
        "state": state,
        "ports": ports,
    }


def _parse_port(port_el: ET.Element) -> dict[str, Any]:
    port_num = int(port_el.get("portid", 0))
    transport = port_el.get("protocol", "")

    state_el = port_el.find("state")
    port_state = state_el.get("state", "unknown") if state_el is not None else "unknown"

    service_name = ""
    service_version = ""
    service_el = port_el.find("service")
    if service_el is not None:
        service_name = service_el.get("name", "")
        product = service_el.get("product", "")
        ver = service_el.get("version", "")
        service_version = f"{product} {ver}".strip()

    result: dict[str, Any] = {
        "port": port_num,
        "transport": transport,
        "state": port_state,
        "service": service_name,
        "service_version": service_version,
    }

    # HTTP/2 via service name (before script loop)
    if service_name == "http2":
        result["http_version"] = "http/2"

    # Parse known scripts
    for script_el in port_el.findall("script"):
        script_id = script_el.get("id", "")

        if script_id == "ssl-enum-ciphers":
            found_versions = [
                k
                for table in script_el.findall("table")
                if (k := table.get("key", "")) in _TLS_VERSION_RANK
            ]
            if found_versions:
                result["tls"] = True
                result["tls_version"] = max(
                    found_versions, key=lambda v: _TLS_VERSION_RANK[v]
                )

        elif script_id == "ssh2-enum-algos":
            algos = [
                elem.text
                for table in script_el.findall("table")
                for elem in table.findall("elem")
                if elem.text
            ]
            if algos:
                result["ssh_algorithms"] = ",".join(algos)

        elif script_id == "http-methods":
            if "http_version" not in result:
                result["http_version"] = "http/1.1"

        elif script_id == "vulners":
            cves = list(
                dict.fromkeys(
                    cve
                    for elem in script_el.iter("elem")
                    if elem.text
                    for cve in re.findall(r"CVE-\d{4}-\d+", elem.text)
                )
            )
            if cves:
                result["cve_ids"] = ",".join(cves)

    return result
