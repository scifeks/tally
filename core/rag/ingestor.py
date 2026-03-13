"""Finding ingestion pipeline — converts ToolResult output into ChromaDB documents."""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.tools.base import ToolResult
from core.tools.constants import (
    CONFIDENCE_CONFIRMED,
    SEVERITY_HIGH,
    SEVERITY_INFORMATIONAL,
    TOOL_DOMAIN_MAP,
    TOOL_TYPE_MAP,
)

from .engine import RAGEngine

logger = logging.getLogger(__name__)


class FindingIngestor:
    """Ingests tool findings into the project's ChromaDB collection.

    Uses a delete-insert (upsert) strategy: before adding new findings for a
    given tool/profile combination the existing ones are removed, so re-running
    a scan never produces duplicates.

    Document ID format::

        <tool>_<profile>_<type>_<indices>_<compact_utc>
        nmap_webservers_host_0_20240228T143022
        nmap_webservers_port_0_3_20240228T143022
    """

    def __init__(self, rag_engine: RAGEngine, project_name: str) -> None:
        """Initialise the ingestor.

        Args:
            rag_engine:   Initialised RAGEngine for the current project.
            project_name: Identifier for the project (used for logging).
        """
        self._engine = rag_engine
        self.project_name = project_name

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_tool_output(
        self,
        tool_result: ToolResult,
        profile: str | None = None,
    ) -> list[str]:
        """Index a tool's findings into ChromaDB.

        Old findings for the same tool/profile are deleted before new ones are
        added, ensuring the collection always reflects the latest scan.

        Args:
            tool_result: Result object returned by the tool executor.
            profile:     Optional profile name (e.g. nmap profile). Defaults
                         to ``"manual"`` for ad-hoc invocations.

        Returns:
            List of document IDs ingested (empty list if nothing to ingest).
        """
        tool = tool_result.tool_name
        effective_profile = profile or "manual"

        if not tool_result.success or tool_result.parsed_data is None:
            logger.warning(
                "Skipping ingestion for %s/%s: "
                "tool did not succeed or produced no parsed data",
                tool,
                effective_profile,
            )
            return []

        if "error" in tool_result.parsed_data:
            logger.warning(
                "Skipping ingestion for %s/%s: parse error — %s",
                tool,
                effective_profile,
                tool_result.parsed_data["error"],
            )
            return []

        # Delete stale findings for this tool/profile before inserting fresh ones
        deleted = self._engine.delete_findings(tool, effective_profile)
        if deleted:
            logger.debug(
                "Deleted %d stale findings for %s/%s", deleted, tool, effective_profile
            )

        chunks = self._build_chunks(tool_result, effective_profile)

        if not chunks:
            logger.info("No findings to ingest for %s/%s", tool, effective_profile)
            return []

        texts, metadatas, ids = zip(*chunks)
        self._engine.add_documents(list(texts), list(metadatas), list(ids))
        logger.info(
            "Ingested %d documents for %s/%s", len(chunks), tool, effective_profile
        )
        return list(ids)

    # ------------------------------------------------------------------
    # Chunk builders
    # ------------------------------------------------------------------

    def _shared_meta(self, tool_name: str, finding_type: str) -> dict[str, Any]:
        """Return shared metadata fields for a given tool/finding_type combination."""
        _sca_flags = {"type_dependency", "type_vulnerability"}
        _TYPE_FLAGS: dict[tuple[str, str], set[str]] = {
            ("gitleaks", "secret"): {"type_secret"},
            ("semgrep", "vulnerability"): {"type_vulnerability", "type_weakness"},
            ("zap", "vulnerability"): {"type_vulnerability"},
            ("nmap", "informational"): set(),
            ("pip-audit", "dependency"): _sca_flags,
            ("npm-audit", "dependency"): _sca_flags,
            ("osv-scanner", "dependency"): _sca_flags,
            ("composer-audit", "dependency"): _sca_flags,
        }
        true_flags = _TYPE_FLAGS.get((tool_name, finding_type), set())
        booleans = {
            f"type_{t}": (f"type_{t}" in true_flags)
            for t in (
                "secret",
                "vulnerability",
                "weakness",
                "misconfiguration",
                "exposure",
                "dependency",
                "informational",
            )
        }
        return {
            "domain": TOOL_DOMAIN_MAP[tool_name],
            "tool_type": TOOL_TYPE_MAP[tool_name],
            "enriched": False,
            **booleans,
        }

    def _build_chunks(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Dispatch to the appropriate per-tool chunk builder.

        Args:
            tool_result: Parsed tool result.
            profile:     Effective profile name.

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        tool = tool_result.tool_name
        if tool == "nmap":
            return self._chunks_from_nmap(tool_result, profile)
        if tool == "semgrep":
            return self._chunks_from_semgrep(tool_result, profile)
        if tool in ("osv-scanner", "pip-audit", "npm-audit", "composer-audit"):
            return self._chunks_from_sca_vulns(tool_result, profile)
        if tool == "gitleaks":
            return self._chunks_from_gitleaks(tool_result, profile)
        if tool == "zap":
            return self._chunks_from_zap(tool_result, profile)

        logger.debug("No chunk builder for tool '%s'; skipping ingestion", tool)
        return []

    def _chunks_from_nmap(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Build document chunks from an nmap ToolResult.

        Each host produces one ``informational`` chunk; each open port on that
        host produces an additional ``informational`` chunk.

        Args:
            tool_result: Parsed nmap result.
            profile:     Effective profile name.

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed: dict[str, Any] = tool_result.parsed_data or {}  # type: ignore[union-attr]
        hosts: list[dict[str, Any]] = parsed.get("hosts", [])
        scan_info: dict[str, Any] = parsed.get("scan_info", {})

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
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
            host_meta: dict[str, Any] = {
                "tool": "nmap",
                "profile": profile,
                "finding_type": "informational",
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
            host_meta.update(self._shared_meta("nmap", "informational"))
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
                    "finding_type": "informational",
                    "ip_address": ip,
                    "port": port_num,
                    "service": service,
                    "transport": transport,
                    "service_version": service_version,
                    "state": "open",
                    "timestamp": timestamp,
                    "source_file": source_file,
                }
                port_meta.update(self._shared_meta("nmap", "informational"))
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

    def _chunks_from_semgrep(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Build document chunks from a semgrep ToolResult.

        Each finding produces one ``vulnerability`` chunk containing the rule
        ID, severity, message, file path, and code snippet.

        Args:
            tool_result: Parsed semgrep result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed: dict[str, Any] = tool_result.parsed_data or {}  # type: ignore[union-attr]
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for fi, finding in enumerate(findings):
            rule_id = finding.get("rule_id", "")
            severity = finding.get("severity", "low")
            message = finding.get("message", "")
            file_path = finding.get("file_path", "")
            line_start = finding.get("line_start", 0)
            col_start = finding.get("col_start")
            line_end = finding.get("line_end", 0)
            col_end = finding.get("col_end")
            code_snippet = finding.get("code_snippet", "")
            fix = finding.get("fix")
            fingerprint = finding.get("fingerprint")
            cwe = finding.get("cwe") or ""
            owasp = finding.get("owasp") or ""
            confidence = finding.get("confidence") or ""
            category = finding.get("category") or ""
            technology: list[str] = finding.get("technology") or []
            subcategory: list[str] = finding.get("subcategory") or []
            likelihood = finding.get("likelihood") or ""
            impact = finding.get("impact") or ""
            references: list[str] = finding.get("references") or []

            text = (
                f"[semgrep] [{severity.upper()}] {rule_id} "
                f"in {file_path}:{line_start}\n"
                f"Message: {message}\n"
                f"Code: {code_snippet}"
            )

            meta: dict[str, Any] = {
                "tool": "semgrep",
                "profile": profile,
                "finding_type": "vulnerability",
                "severity": severity,
                "rule_id": rule_id,
                "file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if col_start is not None:
                meta["col_start"] = col_start
            if col_end is not None:
                meta["col_end"] = col_end
            if cwe:
                meta["cwe"] = cwe
            if owasp:
                meta["owasp"] = owasp
            if confidence:
                meta["confidence"] = confidence
            if fix:
                meta["fix"] = fix
            if fingerprint:
                meta["fingerprint"] = fingerprint
            if category:
                meta["category"] = category
            if technology:
                meta["technology"] = ", ".join(technology)
            if subcategory:
                meta["subcategory"] = ", ".join(subcategory)
            if likelihood:
                meta["likelihood"] = likelihood
            if impact:
                meta["impact"] = impact
            if references:
                meta["references"] = ", ".join(references)
            meta.update(self._shared_meta("semgrep", "vulnerability"))

            doc_id = f"semgrep_{profile}_finding_{fi}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _chunks_from_sca_vulns(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Build document chunks from any SCA tool that emits the standard
        vulnerability format.

        Handles osv-scanner, pip-audit, npm-audit, and composer-audit, all of
        which produce ``{vulnerabilities: [...], summary: {...}}`` output.

        Each vulnerability produces one ``dependency`` chunk containing the
        package name, version, advisory ID, severity, and description.

        Args:
            tool_result: Parsed SCA tool result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        tool = tool_result.tool_name
        parsed: dict[str, Any] = tool_result.parsed_data or {}  # type: ignore[union-attr]
        vulnerabilities: list[dict[str, Any]] = parsed.get("vulnerabilities", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        # Safe ID prefix: replace hyphens so doc IDs have consistent format
        tool_id = tool.replace("-", "_")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for vi, vuln in enumerate(vulnerabilities):
            pkg_name = vuln.get("package_name", "")
            pkg_version = vuln.get("package_version", "")
            vuln_id = vuln.get("vulnerability_id", "")
            aliases: list[str] = vuln.get("aliases") or []
            severity = vuln.get("severity", "low")
            summary = vuln.get("summary", "")
            ecosystem = vuln.get("affected_ecosystem", "")
            fixed_version = vuln.get("fixed_version")
            introduced_version = vuln.get("introduced_version")
            cvss_score = vuln.get("cvss_score")
            cvss_vector = vuln.get("cvss_vector", "")
            lockfile = vuln.get("source_file", "")
            source_type = vuln.get("source_type", "")
            details = vuln.get("details", "")
            published = vuln.get("published", "")
            modified = vuln.get("modified", "")
            references: list[str] = vuln.get("references") or []
            cwe_ids: list[str] = vuln.get("cwe_ids") or []

            fixed_str = fixed_version or "unknown"
            text = (
                f"[{tool}] [{severity.upper()}] vulnerability"
                f" in {pkg_name}@{pkg_version}\n"
                f"Vulnerability: {vuln_id}\n"
                f"Description: {summary}\n"
                f"Ecosystem: {ecosystem}\n"
                f"Fixed in: {fixed_str}\n"
                f"Source: {lockfile}"
            )

            meta: dict[str, Any] = {
                "tool": tool,
                "profile": profile,
                "finding_type": "dependency",
                "severity": severity,
                "package_name": pkg_name,
                "package_version": pkg_version,
                "vulnerability_id": vuln_id,
                "ecosystem": ecosystem,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if aliases:
                meta["aliases"] = ", ".join(aliases)
            if fixed_version:
                meta["fixed_version"] = fixed_version
            if introduced_version:
                meta["introduced_version"] = introduced_version
            if cvss_score is not None:
                meta["cvss_score"] = cvss_score
            if cvss_vector:
                meta["cvss_vector"] = cvss_vector
            if lockfile:
                meta["lockfile"] = lockfile
            if source_type:
                meta["source_type"] = source_type
            if details:
                meta["details"] = details
            if published:
                meta["published"] = published
            if modified:
                meta["modified"] = modified
            if references:
                meta["references"] = ", ".join(references)
            if cwe_ids:
                meta["cwe_ids"] = ", ".join(cwe_ids)
            meta.update(self._shared_meta(tool, "dependency"))

            doc_id = f"{tool_id}_{profile}_vuln_{vi}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _chunks_from_gitleaks(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Build document chunks from a gitleaks ToolResult.

        Each detected secret produces one ``secret`` chunk containing the rule
        ID, file path, line number, and match pattern.  The actual secret value
        is never included in any chunk or metadata.

        Args:
            tool_result: Parsed gitleaks result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed: dict[str, Any] = tool_result.parsed_data or {}  # type: ignore[union-attr]
        secrets: list[dict[str, Any]] = parsed.get("secrets", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for si, secret in enumerate(secrets):
            rule_id = secret.get("rule_id", "")
            description = secret.get("description", "")
            file_path = secret.get("file_path", "")
            line_number = secret.get("line_number", 0)
            end_line = secret.get("end_line", 0)
            start_column = secret.get("start_column", 0)
            end_column = secret.get("end_column", 0)
            entropy = secret.get("entropy")
            author = secret.get("author", "")
            email = secret.get("email", "")
            date = secret.get("date", "")
            message = secret.get("message", "")
            commit = secret.get("commit")
            symlink_file = secret.get("symlink_file")
            tags: list[str] = secret.get("tags") or []
            fingerprint = secret.get("fingerprint", "")

            tags_str = ", ".join(tags) if tags else ""

            text = (
                f"[gitleaks] Secret detected: {rule_id} in {file_path}:{line_number}\n"
                f"Type: {description}\n"
                f"Tags: {tags_str}\n"
                "Note: Secret value redacted"
            )

            meta: dict[str, Any] = {
                "tool": "gitleaks",
                "profile": profile,
                "finding_type": "secret",
                "severity": SEVERITY_HIGH,
                "confidence": CONFIDENCE_CONFIRMED,
                "rule_id": rule_id,
                "file_path": file_path,
                "line_number": line_number,
                "tags": tags_str,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if rule_id:
                meta["risk_type"] = rule_id
            if end_line:
                meta["end_line"] = end_line
            if start_column:
                meta["start_column"] = start_column
            if end_column:
                meta["end_column"] = end_column
            if entropy is not None:
                meta["entropy"] = entropy
            if author:
                meta["author"] = author
            if email:
                meta["email"] = email
            if date:
                meta["date"] = date
            if message:
                meta["message"] = message
            if commit:
                meta["commit"] = commit
            if symlink_file:
                meta["symlink_file"] = symlink_file
            if fingerprint:
                meta["fingerprint"] = fingerprint
            meta.update(self._shared_meta("gitleaks", "secret"))

            doc_id = f"gitleaks_{profile}_secret_{si}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _chunks_from_zap(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Build document chunks from a ZAP ToolResult.

        Each alert instance produces one ``vulnerability`` chunk containing the
        risk level, affected endpoint, description, and remediation advice.

        Args:
            tool_result: Parsed ZAP result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed: dict[str, Any] = tool_result.parsed_data or {}  # type: ignore[union-attr]
        alerts: list[dict[str, Any]] = parsed.get("alerts", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for ai, alert in enumerate(alerts):
            alert_name = alert.get("alert_name", "")
            risk = alert.get("risk", "informational")
            raw_confidence = alert.get("confidence", "low")
            description = alert.get("description", "")
            url = alert.get("url", "")
            method = alert.get("method", "")
            param = alert.get("param") or ""
            evidence = alert.get("evidence") or ""
            solution = alert.get("solution", "")
            cwe_id = alert.get("cwe_id")

            # Map ZAP confidence (text or integer string) to our constants
            _ZAP_CONFIDENCE: dict[str, str] = {
                "confirmed": CONFIDENCE_CONFIRMED,
                "4": CONFIDENCE_CONFIRMED,
                "high": "probable",
                "3": "probable",
                "medium": "probable",
                "2": "probable",
                "low": "potential",
                "1": "potential",
                "false positive": "potential",
                "0": "potential",
            }
            confidence = _ZAP_CONFIDENCE.get(str(raw_confidence).lower(), "potential")

            text_lines = [
                f"[zap] [{risk.upper()}] API vulnerability: {alert_name}",
                f"Endpoint: {method} {url}",
            ]
            if param:
                text_lines.append(f"Parameter: {param}")
            text_lines.append(f"Description: {description}")
            if evidence:
                text_lines.append(f"Evidence: {evidence}")
            text_lines.append(f"Solution: {solution}")
            text = "\n".join(text_lines)

            meta: dict[str, Any] = {
                "tool": "zap",
                "profile": profile,
                "finding_type": "vulnerability",
                "severity": risk,
                "confidence": confidence,
                "risk_type": alert_name,
                "alert_name": alert_name,
                "url": url,
                "method": method.upper(),
                "description": description,
                "remediation": solution,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if param:
                meta["param"] = param
            if cwe_id is not None:
                meta["cwe_id"] = cwe_id
            meta.update(self._shared_meta("zap", "vulnerability"))

            doc_id = f"zap_{profile}_alert_{ai}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _process_finding(
        self,
        finding: dict[str, Any],
        tool_name: str,
        profile: str,
    ) -> tuple[str, dict[str, Any]]:
        """Convert a single finding dict to a (text, metadata) pair.

        Currently a stub; tool-specific logic will be added in Phase 6.

        Args:
            finding:   Structured finding dict from parsed tool output.
            tool_name: Name of the tool that produced the finding.
            profile:   Effective profile name.

        Returns:
            ``(document_text, metadata)`` tuple.
        """
        text = str(finding)
        metadata: dict[str, Any] = {
            "tool": tool_name,
            "profile": profile,
            "finding_type": finding.get("type", "unknown"),
            "timestamp": RAGEngine.now_iso(),
        }
        return text, metadata


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _first_output_file(output_files: dict[str, Path]) -> str:
    """Return the string path of the first output file, or empty string."""
    if not output_files:
        return ""
    return str(next(iter(output_files.values())))
