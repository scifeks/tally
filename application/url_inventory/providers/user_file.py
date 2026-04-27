"""UserFileProvider — convert a user-uploaded endpoint file to UrlFinding rows.

Reuses the existing format-detection + per-format adapters in
``infrastructure/endpoints/converters/`` (which already understand OAS3,
Swagger 2, Postman, HAR, and Katana JSONL). The adapter produces a
normalised OAS3 document; this provider iterates ``paths`` × ``methods``
and yields one ``UrlFinding`` row per operation via the shared
``_oas3_to_findings`` helper.

Each row's ``meta['original_file']`` carries the OAS3 operation object
so the artifact builder can rebuild a faithful merged_oas3.json from
DB rows alone — no need to re-read the source file at scan time.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from application.url_inventory.providers._oas3_to_findings import iter_oas3_rows
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool
from infrastructure.endpoints.converters.service import convert_endpoint_file

if TYPE_CHECKING:
    from application.url_inventory.ports import UrlProviderContext


class UserFileProvider:
    """Provide URL rows from one user-uploaded endpoint file."""

    source: UrlSource = UrlSource.USER
    tool: UrlTool | None = None

    def provide(
        self,
        ctx: UrlProviderContext,
        *,
        file_path: str,
    ) -> Iterable[UrlFinding]:
        """Parse *file_path* and yield ``UrlFinding`` rows."""
        src = Path(file_path)
        oas3_doc = _convert_to_oas3(src)
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


def _convert_to_oas3(src: Path) -> dict:
    """Normalise *src* (any supported format) to an OAS3 dict in memory."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_dir = tmp_path / "out"
        originals_dir = tmp_path / "originals"
        oas3_path = convert_endpoint_file(src, out_dir, originals_dir)
        return json.loads(oas3_path.read_text(encoding="utf-8"))
