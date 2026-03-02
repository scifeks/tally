"""Finding ingestion pipeline — converts ToolResult output into ChromaDB documents."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.tools.base import ToolResult
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
        profile: Optional[str] = None,
    ) -> int:
        """Index a tool's findings into ChromaDB.

        Old findings for the same tool/profile are deleted before new ones are
        added, ensuring the collection always reflects the latest scan.

        Args:
            tool_result: Result object returned by the tool executor.
            profile:     Optional profile name (e.g. nmap profile). Defaults
                         to ``"manual"`` for ad-hoc invocations.

        Returns:
            Number of documents ingested (0 if nothing to ingest).
        """
        tool = tool_result.tool_name
        effective_profile = profile or "manual"

        if not tool_result.success or tool_result.parsed_data is None:
            logger.warning(
                "Skipping ingestion for %s/%s: tool did not succeed or produced no parsed data",
                tool,
                effective_profile,
            )
            return 0

        if "error" in tool_result.parsed_data:
            logger.warning(
                "Skipping ingestion for %s/%s: parse error — %s",
                tool,
                effective_profile,
                tool_result.parsed_data["error"],
            )
            return 0

        # Delete stale findings for this tool/profile before inserting fresh ones
        deleted = self._engine.delete_findings(tool, effective_profile)
        if deleted:
            logger.debug(
                "Deleted %d stale findings for %s/%s", deleted, tool, effective_profile
            )

        chunks = self._build_chunks(tool_result, effective_profile)

        if not chunks:
            logger.info(
                "No findings to ingest for %s/%s", tool, effective_profile
            )
            return 0

        texts, metadatas, ids = zip(*chunks)
        self._engine.add_documents(list(texts), list(metadatas), list(ids))
        logger.info(
            "Ingested %d documents for %s/%s", len(chunks), tool, effective_profile
        )
        return len(chunks)

    # ------------------------------------------------------------------
    # Chunk builders
    # ------------------------------------------------------------------

    def _build_chunks(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> List[Tuple[str, Dict[str, Any], str]]:
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
    ) -> List[Tuple[str, Dict[str, Any], str]]:
        """Build document chunks from an nmap ToolResult.

        Each host produces one ``host`` chunk; each open port on that host
        produces an additional ``open_port`` chunk.

        Args:
            tool_result: Parsed nmap result.
            profile:     Effective profile name.

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed = tool_result.parsed_data  # type: ignore[union-attr]
        hosts: List[Dict[str, Any]] = parsed.get("hosts", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

        chunks: List[Tuple[str, Dict[str, Any], str]] = []

        for host_idx, host in enumerate(hosts):
            ip = host.get("ip_address", "")
            hostname = host.get("hostname", "")
            state = host.get("state", "unknown")
            ports: List[Dict[str, Any]] = host.get("ports", [])
            open_ports = [p for p in ports if p.get("state") == "open"]

            # ---- host chunk ----
            port_lines = "\n".join(
                f"  {p['port']}/{p.get('protocol','tcp')} {p.get('service','')} {p.get('version','')}".rstrip()
                for p in open_ports
            ) or "  (none)"

            host_label = f"{ip} ({hostname})" if hostname else ip
            host_text = (
                f"Host: {host_label}\n"
                f"Status: {state}\n"
                f"Ports:\n{port_lines}"
            )
            host_meta: Dict[str, Any] = {
                "tool": "nmap",
                "profile": profile,
                "finding_type": "host",
                "ip_address": ip,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            host_id = f"nmap_{profile}_host_{host_idx}_{ts_compact}"
            chunks.append((host_text, host_meta, host_id))

            # ---- per-port chunks ----
            for port_idx, port in enumerate(open_ports):
                port_num = port.get("port", 0)
                protocol = port.get("protocol", "tcp")
                service = port.get("service", "")
                version = port.get("version", "")
                svc_str = f"{service} {version}".strip()

                port_text = f"Port {port_num}/{protocol} on {ip}: {svc_str}"
                port_meta: Dict[str, Any] = {
                    "tool": "nmap",
                    "profile": profile,
                    "finding_type": "open_port",
                    "ip_address": ip,
                    "port": port_num,
                    "service": service,
                    "timestamp": timestamp,
                    "source_file": source_file,
                }
                port_id = f"nmap_{profile}_port_{host_idx}_{port_idx}_{ts_compact}"
                chunks.append((port_text, port_meta, port_id))

        return chunks

    def _chunks_from_semgrep(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> List[Tuple[str, Dict[str, Any], str]]:
        """Build document chunks from a semgrep ToolResult.

        Each finding produces one ``vulnerability`` chunk containing the rule
        ID, severity, message, file path, and code snippet.

        Args:
            tool_result: Parsed semgrep result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed = tool_result.parsed_data  # type: ignore[union-attr]
        findings: List[Dict[str, Any]] = parsed.get("findings", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

        chunks: List[Tuple[str, Dict[str, Any], str]] = []

        for fi, finding in enumerate(findings):
            rule_id = finding.get("rule_id", "")
            severity = finding.get("severity", "low")
            message = finding.get("message", "")
            file_path = finding.get("file_path", "")
            line_start = finding.get("line_start", 0)
            line_end = finding.get("line_end", 0)
            code_snippet = finding.get("code_snippet", "")
            cwe = finding.get("cwe") or ""
            owasp = finding.get("owasp") or ""

            text = (
                f"[{severity.upper()}] {rule_id} in {file_path}:{line_start}\n"
                f"Message: {message}\n"
                f"Code: {code_snippet}"
            )

            meta: Dict[str, Any] = {
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
            if cwe:
                meta["cwe"] = cwe
            if owasp:
                meta["owasp"] = owasp

            doc_id = f"semgrep_{profile}_finding_{fi}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _chunks_from_sca_vulns(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> List[Tuple[str, Dict[str, Any], str]]:
        """Build document chunks from any SCA tool that emits the standard vulnerability format.

        Handles osv-scanner, pip-audit, npm-audit, and composer-audit, all of
        which produce ``{vulnerabilities: [...], summary: {...}}`` output.

        Each vulnerability produces one ``dependency_vulnerability`` chunk
        containing the package name, version, advisory ID, severity, and
        description.

        Args:
            tool_result: Parsed SCA tool result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        tool = tool_result.tool_name
        parsed = tool_result.parsed_data  # type: ignore[union-attr]
        vulnerabilities: List[Dict[str, Any]] = parsed.get("vulnerabilities", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        # Safe ID prefix: replace hyphens so doc IDs have consistent format
        tool_id = tool.replace("-", "_")

        chunks: List[Tuple[str, Dict[str, Any], str]] = []

        for vi, vuln in enumerate(vulnerabilities):
            pkg_name = vuln.get("package_name", "")
            pkg_version = vuln.get("package_version", "")
            vuln_id = vuln.get("vulnerability_id", "")
            severity = vuln.get("severity", "low")
            summary = vuln.get("summary", "")
            ecosystem = vuln.get("affected_ecosystem", "")
            fixed_version = vuln.get("fixed_version")
            cvss_score = vuln.get("cvss_score")
            lockfile = vuln.get("source_file", "")

            fixed_str = fixed_version or "unknown"
            text = (
                f"[{severity.upper()}] vulnerability in {pkg_name}@{pkg_version}\n"
                f"Vulnerability: {vuln_id}\n"
                f"Description: {summary}\n"
                f"Ecosystem: {ecosystem}\n"
                f"Fixed in: {fixed_str}\n"
                f"Source: {lockfile}"
            )

            meta: Dict[str, Any] = {
                "tool": tool,
                "profile": profile,
                "finding_type": "dependency_vulnerability",
                "severity": severity,
                "package_name": pkg_name,
                "package_version": pkg_version,
                "vulnerability_id": vuln_id,
                "ecosystem": ecosystem,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if fixed_version:
                meta["fixed_version"] = fixed_version
            if cvss_score is not None:
                meta["cvss_score"] = cvss_score
            if lockfile:
                meta["lockfile"] = lockfile

            doc_id = f"{tool_id}_{profile}_vuln_{vi}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _chunks_from_gitleaks(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> List[Tuple[str, Dict[str, Any], str]]:
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
        parsed = tool_result.parsed_data  # type: ignore[union-attr]
        secrets: List[Dict[str, Any]] = parsed.get("secrets", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

        chunks: List[Tuple[str, Dict[str, Any], str]] = []

        for si, secret in enumerate(secrets):
            rule_id = secret.get("rule_id", "")
            description = secret.get("description", "")
            file_path = secret.get("file_path", "")
            line_number = secret.get("line_number", 0)
            match = secret.get("match", "")
            tags: List[str] = secret.get("tags") or []
            commit = secret.get("commit")

            tags_str = ", ".join(tags) if tags else ""

            text = (
                f"Secret detected: {rule_id} in {file_path}:{line_number}\n"
                f"Type: {description}\n"
                f"Pattern matched: {match}\n"
                f"Tags: {tags_str}\n"
                "Note: Actual secret value redacted for security"
            )

            meta: Dict[str, Any] = {
                "tool": "gitleaks",
                "profile": profile,
                "finding_type": "secret",
                "severity": "high",
                "rule_id": rule_id,
                "file_path": file_path,
                "line_number": line_number,
                "tags": tags_str,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if commit:
                meta["commit"] = commit

            doc_id = f"gitleaks_{profile}_secret_{si}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _chunks_from_zap(
        self,
        tool_result: ToolResult,
        profile: str,
    ) -> List[Tuple[str, Dict[str, Any], str]]:
        """Build document chunks from a ZAP ToolResult.

        Each alert instance produces one ``api_vulnerability`` chunk containing
        the risk level, affected endpoint, description, and remediation advice.

        Args:
            tool_result: Parsed ZAP result.
            profile:     Effective profile name (repo name).

        Returns:
            List of ``(document_text, metadata, id)`` tuples.
        """
        parsed = tool_result.parsed_data  # type: ignore[union-attr]
        alerts: List[Dict[str, Any]] = parsed.get("alerts", [])

        timestamp = tool_result.timestamp
        source_file = _first_output_file(tool_result.output_files)
        ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

        chunks: List[Tuple[str, Dict[str, Any], str]] = []

        for ai, alert in enumerate(alerts):
            alert_name = alert.get("alert_name", "")
            risk = alert.get("risk", "informational")
            confidence = alert.get("confidence", "low")
            description = alert.get("description", "")
            url = alert.get("url", "")
            method = alert.get("method", "")
            param = alert.get("param") or ""
            evidence = alert.get("evidence") or ""
            solution = alert.get("solution", "")
            cwe_id = alert.get("cwe_id")

            text_lines = [
                f"[{risk.upper()}] API vulnerability: {alert_name}",
                f"Endpoint: {method} {url}",
            ]
            if param:
                text_lines.append(f"Parameter: {param}")
            text_lines.append(f"Description: {description}")
            if evidence:
                text_lines.append(f"Evidence: {evidence}")
            text_lines.append(f"Solution: {solution}")
            text = "\n".join(text_lines)

            meta: Dict[str, Any] = {
                "tool": "zap",
                "profile": profile,
                "finding_type": "api_vulnerability",
                "severity": risk,
                "confidence": confidence,
                "alert_name": alert_name,
                "url": url,
                "method": method,
                "timestamp": timestamp,
                "source_file": source_file,
            }
            if param:
                meta["param"] = param
            if cwe_id is not None:
                meta["cwe_id"] = cwe_id

            doc_id = f"zap_{profile}_alert_{ai}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def _process_finding(
        self,
        finding: Dict[str, Any],
        tool_name: str,
        profile: str,
    ) -> Tuple[str, Dict[str, Any]]:
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
        metadata: Dict[str, Any] = {
            "tool": tool_name,
            "profile": profile,
            "finding_type": finding.get("type", "unknown"),
            "timestamp": RAGEngine.now_iso(),
        }
        return text, metadata


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _first_output_file(output_files: Dict[str, Path]) -> str:
    """Return the string path of the first output file, or empty string."""
    if not output_files:
        return ""
    return str(next(iter(output_files.values())))
