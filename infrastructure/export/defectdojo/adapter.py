"""DefectDojo export adapter implementing ExportPort."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from application.ports.export import ExportResult
from infrastructure.export.defectdojo.client import DefectDojoClient
from infrastructure.export.defectdojo.mapper import map_findings

if TYPE_CHECKING:
    from core.config.schemas.defectdojo_config import (
        DefectDojoConnectionConfig,
        DefectDojoProjectConfig,
    )
    from domain.findings.entry import Finding

log = logging.getLogger(__name__)


class DefectDojoExportAdapter:
    def __init__(
        self,
        connection: DefectDojoConnectionConfig,
        project: DefectDojoProjectConfig,
    ) -> None:
        self._project = project
        self._client = DefectDojoClient(
            url=connection.url,
            api_token=connection.api_token,
            verify_ssl=connection.verify_ssl,
        )

    def export_findings(self, findings: list[Finding]) -> ExportResult:
        if not findings:
            return ExportResult(
                success=True,
                findings_exported=0,
                findings_failed=0,
            )

        mapped = map_findings(findings)
        failed_count = len(findings) - len(mapped)

        if not mapped:
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=failed_count,
                errors=("All findings failed to map",),
            )

        payload = json.dumps({"name": "Tally Export", "findings": mapped}).encode()

        try:
            status, body = self._client.reimport_scan(
                json_payload=payload,
                scan_type="Generic Findings Import",
                product_name=self._project.product_name,
                engagement_name=self._project.engagement_name,
                product_type_name=self._project.product_type_name,
                auto_create_context=self._project.auto_create_context,
            )
        except Exception as exc:
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=len(findings),
                errors=(f"Connection error: {exc}",),
            )

        if status == 401 or status == 403:
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=len(findings),
                errors=("Authentication failed: invalid or expired API token",),
            )

        if status >= 400:
            error_detail = json.dumps(body) if body else str(status)
            return ExportResult(
                success=False,
                findings_exported=0,
                findings_failed=len(findings),
                errors=(f"DefectDojo returned {status}: {error_detail}",),
            )

        log.info(
            "Exported %d findings to DefectDojo (%d failed to map)",
            len(mapped),
            failed_count,
        )
        return ExportResult(
            success=True,
            findings_exported=len(mapped),
            findings_failed=failed_count,
        )

    def test_connection(self) -> bool:
        return self._client.test_connection()
