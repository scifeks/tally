"""NmapHandler — converts nmap ToolResult into normalized finding dicts."""

import json
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import CONFIDENCE_CONFIRMED, SEVERITY_INFORMATIONAL

from ._shared import _first_output_file, _shared_meta


class NmapChunkBuilder:
    tool_name = "nmap"
    domain = "network"
    segment = "network"
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence", "risk_type", "remediation", "description"}
    )
    type_flags: dict[str, set[str]] = {"exposure": {"type_exposure"}}
    should_enrich = False
    enrichment_fields = None

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        hosts: list[dict[str, Any]] = parsed.get("hosts", [])
        scan_info: dict[str, Any] = parsed.get("scan_info", {})

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        nmap_version = scan_info.get("version", "")
        nmap_args = scan_info.get("args", "")
        scan_start_time = scan_info.get("start_time", "")

        rows: list[dict] = []

        for host in hosts:
            if host.get("state") != "up":
                continue
            ip = host.get("ip_address", "")
            ports: list[dict[str, Any]] = host.get("ports", [])
            open_ports = [p for p in ports if p.get("state") == "open"]

            if not open_ports:
                # Host is up but has no open ports — one host-only row
                row: dict[str, Any] = {
                    "tool": "nmap",
                    "profile": profile,
                    "finding_type": json.dumps(["exposure"]),
                    "confidence": CONFIDENCE_CONFIRMED,
                    "severity": SEVERITY_INFORMATIONAL,
                    "ip_address": ip,
                    "timestamp": timestamp,
                    "source_file": source_file,
                }
                if nmap_version:
                    row["nmap_version"] = nmap_version
                if nmap_args:
                    row["nmap_args"] = nmap_args
                if scan_start_time:
                    row["scan_start_time"] = scan_start_time
                row.update(_shared_meta(self, "exposure"))
                rows.append(row)
                continue

            for port in open_ports:
                port_num = port.get("port", 0)
                transport = port.get("transport", "tcp")
                service = port.get("service", "")
                service_version = port.get("service_version", "")
                svc_str = f"{service} {service_version}".strip()

                row = {
                    "tool": "nmap",
                    "profile": profile,
                    "finding_type": json.dumps(["exposure"]),
                    "confidence": CONFIDENCE_CONFIRMED,
                    "severity": SEVERITY_INFORMATIONAL,
                    "ip_address": ip,
                    "port": port_num,
                    "service": service,
                    "transport": transport,
                    "service_version": service_version,
                    "state": "open",
                    "timestamp": timestamp,
                    "source_file": source_file,
                }
                if svc_str:
                    row["description"] = f"{svc_str} service open on port {port_num}"
                if nmap_version:
                    row["nmap_version"] = nmap_version
                if nmap_args:
                    row["nmap_args"] = nmap_args
                if scan_start_time:
                    row["scan_start_time"] = scan_start_time
                for key in (
                    "tls",
                    "tls_version",
                    "http_version",
                    "ssh_algorithms",
                    "cve_ids",
                ):
                    val = port.get(key)
                    if val is not None:
                        row[key] = val
                row.update(_shared_meta(self, "exposure"))
                rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [f"Host: {row.get('ip_address', '')}"]
        if row.get("port") is not None:
            transport = row.get("transport", "tcp")
            parts.append(f"Port: {row['port']}/{transport}")
            parts.append(f"Service: {row.get('service', '')}")
            parts.append("State: open")
            if row.get("service_version"):
                parts.append(f"Version: {row['service_version']}")
            if row.get("description"):
                parts.append(f"Description: {row['description']}")
            if row.get("tls_version"):
                parts.append(f"TLS version: {row['tls_version']}")
            if row.get("cve_ids"):
                parts.append(f"CVEs: {row['cve_ids']}")
        else:
            parts.append("State: up (no open ports)")
        return "[nmap] " + " | ".join(parts)
