"""Convert apidocs pipeline output into UrlFinding rows.

The pipeline produces an OAS3 JSON document. This provider reads it
via the shared iter_oas3_rows helper and yields scan-source rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from application.url_inventory.providers._oas3_to_findings import (
    iter_oas3_rows,
)
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool

if TYPE_CHECKING:
    from application.url_inventory.ports import UrlProviderContext


class ApidocsProvider:
    """Provide URL rows from an apidocs-produced OAS3 file."""

    source: UrlSource = UrlSource.SCAN
    tool: UrlTool | None = UrlTool.APIDOCS

    def provide(
        self,
        ctx: UrlProviderContext,
        *,
        file_path: str,
    ) -> Iterable[UrlFinding]:
        src = Path(file_path)
        if not src.exists():
            return []
        try:
            doc = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(doc, dict):
            return []
        return list(
            iter_oas3_rows(
                doc,
                ctx,
                source=UrlSource.SCAN,
                tool=UrlTool.APIDOCS,
                run_id=ctx.run_id,
                file_path=None,
            )
        )
