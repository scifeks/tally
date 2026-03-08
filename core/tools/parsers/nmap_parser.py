import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


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
    protocol = port_el.get("protocol", "")

    state_el = port_el.find("state")
    port_state = state_el.get("state", "unknown") if state_el is not None else "unknown"

    service_name = ""
    version = ""
    service_el = port_el.find("service")
    if service_el is not None:
        service_name = service_el.get("name", "")
        product = service_el.get("product", "")
        ver = service_el.get("version", "")
        version = f"{product} {ver}".strip()

    return {
        "port": port_num,
        "protocol": protocol,
        "state": port_state,
        "service": service_name,
        "version": version,
    }
