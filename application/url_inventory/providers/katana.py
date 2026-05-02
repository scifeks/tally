"""Convert Katana scan output into UrlFinding rows.

Katana writes an OAS3 document under ``tool_outputs/katana/``. This
provider parses it via the shared ``iter_oas3_rows`` helper. Each row
carries source=UrlSource.SCAN, tool=UrlTool.KATANA, and the scan run id.
The per-operation OAS3 object is preserved in ``meta.original_file`` so
the artifact builder can rebuild a faithful ``merged_oas3.json`` later.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from application.url_inventory.providers._oas3_to_findings import iter_oas3_rows
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool

if TYPE_CHECKING:
    from application.url_inventory.ports import UrlProviderContext


class KatanaProvider:
    """Provide URL rows from a Katana-produced OAS3 file."""

    source: UrlSource = UrlSource.SCAN
    tool: UrlTool | None = UrlTool.KATANA

    def provide(
        self,
        ctx: UrlProviderContext,
        *,
        file_path: str,
    ) -> Iterable[UrlFinding]:
        """Parse the OAS3 file at *file_path* and yield ``UrlFinding`` rows.

        *file_path* must point at the OAS3 JSON file produced by Katana.
        Per-row ``file_path`` is left as ``None`` because scan-source rows
        are tied to ``run_id`` rather than a stable on-disk artifact; the
        original_file fragment in ``meta`` is the durable record.
        """
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
                tool=UrlTool.KATANA,
                run_id=ctx.run_id,
                file_path=None,
            )
        )
