"""DefectDojo export adapter implementing ExportPort."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from application.ports.export import ExportResult
from infrastructure.export.defectdojo.client import DefectDojoClient
from infrastructure.export.defectdojo.mapper import (
    _is_static_asset_path,
    map_findings,
)

if TYPE_CHECKING:
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from core.config.schemas.defectdojo_config import (
        DefectDojoGlobalConfig,
    )
    from domain.findings.entry import Finding

log = logging.getLogger(__name__)


class DefectDojoExportAdapter:
    def __init__(
        self,
        config: DefectDojoGlobalConfig,
        repo_names: dict[int, str],
        project_name: str,
        engagement_type: str,
        run_to_repo_id: dict[int, int] | None = None,
        all_tool_runs: set[tuple[int | None, str]] | None = None,
        url_finding_repo: UrlFindingRepositoryPort | None = None,
        repo_base_urls: dict[int, list[str]] | None = None,
    ) -> None:
        self._config = config
        self._repo_names = repo_names
        self._project_name = project_name
        self._engagement_type = engagement_type
        self._run_to_repo_id = run_to_repo_id or {}
        self._all_tool_runs = all_tool_runs or set()
        self._url_finding_repo = url_finding_repo
        self._repo_base_urls = repo_base_urls
        self._client = DefectDojoClient(
            url=config.url,
            api_token=config.api_token,
            verify_ssl=config.verify_ssl,
        )

    def export_findings(self, findings: list[Finding]) -> ExportResult:
        repo_groups: dict[int | None, dict[str, list[Finding]]] = {}
        for f in findings:
            repo_id = self._effective_repo_id(f)
            if repo_id not in repo_groups:
                repo_groups[repo_id] = {}
            tool_key = f.tool or "unknown"
            repo_groups[repo_id].setdefault(tool_key, []).append(f)

        total_exported = 0
        total_failed = 0
        errors: list[str] = []
        seen_pairs: set[tuple[int | None, str]] = set()

        for repo_id, tool_groups in repo_groups.items():
            product_name = self._product_name(repo_id)
            for tool_name, tool_findings in tool_groups.items():
                seen_pairs.add((repo_id, tool_name))
                result = self._reimport_tool_group(
                    tool_name, tool_findings, product_name
                )
                total_exported += result.findings_exported
                total_failed += result.findings_failed
                errors.extend(result.errors)
                if self._is_auth_error(result):
                    return result

        for repo_id, tool_name in self._all_tool_runs - seen_pairs:
            product_name = self._product_name(repo_id)
            result = self._reimport_empty(tool_name, product_name)
            errors.extend(result.errors)
            if self._is_auth_error(result):
                return result

        self._export_endpoints()

        return ExportResult(
            success=not errors,
            findings_exported=total_exported,
            findings_failed=total_failed,
            errors=tuple(errors),
        )

    def _effective_repo_id(self, f: Finding) -> int | None:
        if f.repo_id is not None:
            return f.repo_id
        if f.run_id is not None:
            return self._run_to_repo_id.get(f.run_id)
        return None

    def _product_name(self, repo_id: int | None) -> str:
        if repo_id is not None and repo_id in self._repo_names:
            repo_name = self._repo_names[repo_id]
        else:
            repo_name = "Unassociated"
        return f"{self._project_name} / {repo_name}"

    def _reimport_tool_group(
        self,
        tool_name: str,
        findings: list[Finding],
        product_name: str,
    ) -> ExportResult:
        mapped = map_findings(findings)
        map_failed = len(findings) - len(mapped)

        if not mapped:
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=map_failed,
                errors=(f"{tool_name}: all findings failed to map",),
            )

        return self._send_reimport(tool_name, mapped, product_name, map_failed)

    def _reimport_empty(self, tool_name: str, product_name: str) -> ExportResult:
        return self._send_reimport(tool_name, [], product_name, 0)

    def _send_reimport(
        self,
        tool_name: str,
        mapped: list[dict],
        product_name: str,
        map_failed: int,
    ) -> ExportResult:
        payload = json.dumps({"findings": mapped}).encode()

        try:
            status, body = self._client.reimport_scan(
                json_payload=payload,
                scan_type=self._config.scan_type,
                product_name=product_name,
                engagement_name=self._engagement_type,
                product_type_name=self._config.product_type,
                auto_create_context=self._config.auto_create_context,
                test_title=tool_name,
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=len(mapped) + map_failed,
                errors=(f"{tool_name}: connection error: {exc}",),
            )

        if status == 401 or status == 403:
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=len(mapped) + map_failed,
                errors=("Authentication failed: invalid or expired API token",),
            )

        if status >= 400:
            detail = json.dumps(body) if body else str(status)
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=len(mapped) + map_failed,
                errors=(f"{tool_name}: DefectDojo returned {status}: {detail}",),
            )

        log.info(
            "Exported %d %s findings to %s (%d failed to map)",
            len(mapped),
            tool_name,
            product_name,
            map_failed,
        )
        return ExportResult(
            success=True,
            findings_exported=len(mapped),
            findings_failed=map_failed,
        )

    def _export_endpoints(self) -> None:
        if self._url_finding_repo is None or self._repo_base_urls is None:
            return

        try:
            for repo_id in self._repo_names:
                allowed: set[tuple[str, int]] = set()
                for base_url in self._repo_base_urls.get(repo_id, []):
                    parsed = urlparse(base_url)
                    host = parsed.hostname or ""
                    port = parsed.port or (443 if parsed.scheme == "https" else 80)
                    if host:
                        allowed.add((host, port))

                if not allowed:
                    continue

                product_id = self._client.get_product_id(self._product_name(repo_id))
                if product_id is None:
                    continue

                url_findings = self._url_finding_repo.list_for_repo(repo_id)

                seen: set[tuple[str, str, int, str]] = set()
                endpoints_created = 0
                for uf in url_findings:
                    if (uf.host, uf.port) not in allowed:
                        continue
                    if _is_static_asset_path(uf.path):
                        continue
                    key = (uf.protocol, uf.host, uf.port, uf.path)
                    if key in seen:
                        continue
                    seen.add(key)
                    self._client.create_endpoint(
                        product_id, uf.protocol, uf.host, uf.port, uf.path
                    )
                    endpoints_created += 1

                if endpoints_created > 0:
                    repo_name = self._repo_names.get(repo_id, "Unassociated")
                    log.info(
                        "Exported %d endpoints for repo %s to DefectDojo",
                        endpoints_created,
                        repo_name,
                    )
        except Exception as exc:
            log.warning("Failed to export endpoints to DefectDojo: %s", exc)

    @staticmethod
    def _is_auth_error(result: ExportResult) -> bool:
        return not result.success and any(
            "Authentication failed" in e for e in result.errors
        )

    def test_connection(self) -> bool:
        return self._client.test_connection()
