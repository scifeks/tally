"""NmapChunkBuilder — converts nmap ToolResult into ChromaDB document chunks."""

import json
from datetime import UTC, datetime
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
    type_flags: dict[str, set[str]] = {"informational": set()}
    should_enrich = False

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        hosts: list[dict[str, Any]] = parsed.get("hosts", [])
        scan_info: dict[str, Any] = parsed.get("scan_info", {})

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        nmap_version = scan_info.get("version", "")
        nmap_args = scan_info.get("args", "")
        scan_start_time = scan_info.get("start_time", "")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for host_idx, host in enumerate(hosts):
            ip = host.get("ip_address", "")
            hostname = host.get("hostname", "")
            state = host.get("state", "unknown")
            ports: list[dict[str, Any]] = host.get("ports", [])
            open_ports = [p for p in ports if p.get("state") == "open"]

            # ---- host chunk ----
            port_lines = (
                "\n".join(
                    (
                        f"  {p['port']}/{p.get('transport', 'tcp')} "
                        f"{p.get('service', '')} {p.get('service_version', '')}"
                    ).rstrip()
                    for p in open_ports
                )
                or "  (none)"
            )

            host_label = f"{ip} ({hostname})" if hostname else ip
            host_text = (
                f"[nmap] Host: {host_label}\nStatus: {state}\nPorts:\n{port_lines}"
            )
            # TODO: description not set — nmap parser does not emit a description field
            host_meta: dict[str, Any] = {
                "tool": "nmap",
                "profile": profile,
                "finding_type": json.dumps(["informational"]),
                "confidence": CONFIDENCE_CONFIRMED,
                "ip_address": ip,
                "hostname": hostname,
                "state": state,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if nmap_version:
                host_meta["nmap_version"] = nmap_version
            if nmap_args:
                host_meta["nmap_args"] = nmap_args
            if scan_start_time:
                host_meta["scan_start_time"] = scan_start_time
            host_meta.update(_shared_meta(self, "informational"))
            host_meta["severity"] = SEVERITY_INFORMATIONAL
            host_id = f"nmap_{profile}_host_{host_idx}_{ts_compact}"
            chunks.append((host_text, host_meta, host_id))

            # ---- per-port chunks ----
            for port_idx, port in enumerate(open_ports):
                port_num = port.get("port", 0)
                transport = port.get("transport", "tcp")
                service = port.get("service", "")
                service_version = port.get("service_version", "")
                svc_str = f"{service} {service_version}".strip()

                port_text = f"[nmap] Port {port_num}/{transport} on {ip}: {svc_str}"
                port_meta: dict[str, Any] = {
                    "tool": "nmap",
                    "profile": profile,
                    "finding_type": json.dumps(["informational"]),
                    "confidence": CONFIDENCE_CONFIRMED,
                    "ip_address": ip,
                    "port": port_num,
                    "service": service,
                    "transport": transport,
                    "service_version": service_version,
                    "state": "open",
                    "timestamp": timestamp,
                    "source_file": source_file,
                }
                port_meta.update(_shared_meta(self, "informational"))
                port_meta["severity"] = SEVERITY_INFORMATIONAL
                if nmap_version:
                    port_meta["nmap_version"] = nmap_version
                if nmap_args:
                    port_meta["nmap_args"] = nmap_args
                if scan_start_time:
                    port_meta["scan_start_time"] = scan_start_time
                for key in (
                    "tls",
                    "tls_version",
                    "http_version",
                    "ssh_algorithms",
                    "cve_ids",
                ):
                    val = port.get(key)
                    if val is not None:
                        port_meta[key] = val
                port_id = f"nmap_{profile}_port_{host_idx}_{port_idx}_{ts_compact}"
                chunks.append((port_text, port_meta, port_id))

        return chunks

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "nmap",
                str(finding.get("ip_address", "")),
                str(finding.get("port", "")),
                str(finding.get("transport", "")),
            ]
        )
