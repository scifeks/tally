"""Convert user-uploaded endpoint files to UrlFinding rows.

Reuses format-detection and per-format adapters that understand OAS3,
Swagger 2, Postman, HAR, and Katana JSONL. The adapter produces a
normalised OAS3 document; this provider iterates paths and methods and
yields one UrlFinding row per operation via the shared iter_oas3_rows
helper. Each row's ``meta['original_file']`` preserves the OAS3 operation
object so the artifact builder can rebuild merged_oas3.json from DB rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from application.url_inventory.providers._oas3_to_findings import iter_oas3_rows
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool

if TYPE_CHECKING:
    from application.ports.url_source_converter import UrlSourceConverterPort
    from application.url_inventory.ports import UrlProviderContext


class UserFileProvider:
    """Provide URL rows from one user-uploaded endpoint file."""

    source: UrlSource = UrlSource.USER
    tool: UrlTool | None = None

    def __init__(self, converter: UrlSourceConverterPort) -> None:
        self._converter = converter

    def provide(
        self,
        ctx: UrlProviderContext,
        *,
        file_path: str,
    ) -> Iterable[UrlFinding]:
        """Parse *file_path* and yield ``UrlFinding`` rows."""
        oas3_doc = self._converter.to_oas3(Path(file_path))
        return list(
            iter_oas3_rows(
                oas3_doc,
                ctx,
                source=UrlSource.USER,
                tool=None,
                run_id=None,
                file_path=file_path,
            )
        )
