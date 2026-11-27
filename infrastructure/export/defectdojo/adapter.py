"""DefectDojo export adapter implementing ExportPort."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from application.ports.export import ExportResult
from infrastructure.export.defectdojo.client import DefectDojoClient
from infrastructure.export.defectdojo.mapper import (
    is_static_asset_path,
    map_findings,
)

if TYPE_CHECKING:
    from application.ports.export import SyncBatch
    from application.ports.url_finding_repository import (
        UrlFindingRepositoryPort,
    )
    from core.config.schemas.defectdojo_config import (
        DefectDojoGlobalConfig,
    )

log = logging.getLogger(__name__)

# DefectDojo hard-codes CI/CD when it creates an Engagement on import.
_ENGAGEMENT_TYPE = "Interactive"


class DefectDojoExportAdapter:
    def __init__(
        self,
        config: DefectDojoGlobalConfig,
        repo_names: dict[int, str],
        project_name: str,
        organization_name: str,
        engagement_name: str,
        url_finding_repo: UrlFindingRepositoryPort | None = None,
        repo_base_urls: dict[int, list[str]] | None = None,
    ) -> None:
        self._config = config
        self._repo_names = repo_names
        self._project_name = project_name
        self._organization_name = organization_name
        self._engagement_name = engagement_name
        self._url_finding_repo = url_finding_repo
        self._repo_base_urls = repo_base_urls
        self._client = DefectDojoClient(
            url=config.url,
            api_token=config.api_token,
            verify_ssl=config.verify_ssl,
        )

    def export_batches(self, batches: list[SyncBatch]) -> ExportResult:
        total_exported = 0
        total_failed = 0
        errors: list[str] = []
        typed_repos: set[int] = set()

        for batch in batches:
            product_name = self._product_name(batch.repo_id)
            result, engagement_id = self._send_batch(batch, product_name)
            total_exported += result.findings_exported
            total_failed += result.findings_failed
            errors.extend(result.errors)
            if self._is_auth_error(result):
                return result
            if engagement_id is not None and batch.repo_id not in typed_repos:
                typed_repos.add(batch.repo_id)
                self._mark_interactive(engagement_id, product_name)

        self._export_endpoints()

        return ExportResult(
            success=not errors,
            findings_exported=total_exported,
            findings_failed=total_failed,
            errors=tuple(errors),
        )

    def _product_name(self, repo_id: int) -> str:
        return f"{self._project_name} / {self._repo_names[repo_id]}"

    def _mark_interactive(self, engagement_id: int, product_name: str) -> None:
        if not self._client.set_engagement_type(engagement_id, _ENGAGEMENT_TYPE):
            log.warning(
                "Could not set the Engagement type to %s for %s",
                _ENGAGEMENT_TYPE,
                product_name,
            )

    def _send_batch(
        self, batch: SyncBatch, product_name: str
    ) -> tuple[ExportResult, int | None]:
        findings = list(batch.findings)
        mapped = map_findings(findings)
        map_failed = len(findings) - len(mapped)

        # Sending nothing here would close every finding in the Test.
        if findings and not mapped:
            return (
                ExportResult(
                    success=False,
                    findings_exported=0,
                    findings_failed=map_failed,
                    errors=(f"{batch.tool}: all findings failed to map",),
                ),
                None,
            )

        return self._send_reimport(batch.tool, mapped, product_name, map_failed)

    def _send_reimport(
        self,
        tool_name: str,
        mapped: list[dict],
        product_name: str,
        map_failed: int,
    ) -> tuple[ExportResult, int | None]:
        payload = json.dumps({"findings": mapped}).encode()
        failed = len(mapped) + map_failed

        try:
            status, body = self._client.reimport_scan(
                json_payload=payload,
                scan_type=self._config.scan_type,
                product_name=product_name,
                engagement_name=self._engagement_name,
                product_type_name=self._organization_name,
                auto_create_context=self._config.auto_create_context,
                test_title=tool_name,
            )
        except Exception as exc:
            return _failure(failed, f"{tool_name}: connection error: {exc}"), None

        if status == 401 or status == 403:
            error = "Authentication failed: invalid or expired API token"
            return _failure(failed, error), None

        if status >= 400:
            detail = json.dumps(body) if body else str(status)
            error = f"{tool_name}: DefectDojo returned {status}: {detail}"
            return _failure(failed, error), None

        log.info(
            "Exported %d %s findings to %s (%d failed to map)",
            len(mapped),
            tool_name,
            product_name,
            map_failed,
        )
        engagement_id = body.get("engagement_id")
        return (
            ExportResult(
                success=True,
                findings_exported=len(mapped),
                findings_failed=map_failed,
            ),
            engagement_id if isinstance(engagement_id, int) else None,
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
                    if is_static_asset_path(uf.path):
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
                    repo_name = self._repo_names[repo_id]
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


def _failure(findings_failed: int, error: str) -> ExportResult:
    return ExportResult(
        success=False,
        findings_exported=0,
        findings_failed=findings_failed,
        errors=(error,),
    )
