"""Shared integration sync orchestration."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def run_configured_syncs(
    *,
    base_path: str,
    project_name: str,
    run_id: int,
    sync_list: list[str],
) -> None:
    if not sync_list:
        return
    for integration in sync_list:
        if integration == "defectdojo":
            try:
                _sync_defectdojo(base_path, project_name, run_id)
            except Exception:
                logger.exception(
                    "integration sync: defectdojo sync failed for run %d",
                    run_id,
                )
        else:
            logger.warning(
                "integration sync: unknown integration %r",
                integration,
            )


def _sync_defectdojo(
    base_path: str,
    project_name: str,
    run_id: int,
) -> None:
    from factories.export import (
        create_export_service_for_project,
    )

    service = create_export_service_for_project(
        base_path=base_path,
        project_name=project_name,
        run_id=run_id,
    )
    export_result = service.export()

    if export_result.success:
        logger.info(
            "integration sync: exported %d findings to DefectDojo (run %d)",
            export_result.findings_exported,
            run_id,
        )
    else:
        for error in export_result.errors:
            logger.warning("integration sync: %s", error)
