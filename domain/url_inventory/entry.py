"""URL inventory domain entity.

A ``UrlFinding`` is one entry in the per-project URL inventory: either a
URL discovered by a scan tool (Katana / Noir) or ingested from a
user-provided endpoint file (OAS3, Swagger, Postman, HAR, Katana JSONL).
Separate from the findings table with its own schema and lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class UrlSource(StrEnum):
    """Origin of a URL row.

    - ``SCAN``: discovered by a scan tool (Katana / Noir). ``tool`` is
      required and ``run_id`` carries the scan run.
    - ``USER``: ingested from a user-uploaded endpoint file. ``tool`` is
      ``None`` and ``file_path`` points to the copy under
      ``projects/<p>/endpoints/<repo_uuid>/user_uploads/``.
    """

    SCAN = "scan"
    USER = "user"


class UrlTool(StrEnum):
    """Scan tool that produced a SCAN-source row."""

    KATANA = "katana"
    NOIR = "noir"
    LLM = "llm"


@dataclass(frozen=True)
class UrlFinding:
    """One row in the per-project ``url_findings`` table.

    The ``meta`` dict carries source-format-specific data; in particular
    ``meta['original_file']`` carries the source-format fragment (OAS3
    operation object, HAR entry, Postman request) that produced this row,
    so the artifact builder can rebuild a faithful merged OAS3 document
    purely from DB rows.
    """

    repo_id: int
    source: UrlSource
    tool: UrlTool | None
    run_id: int | None
    method: str
    protocol: str
    host: str
    port: int
    path: str
    file_path: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        # Mirror the SQLite CHECK constraint at the domain layer so violations
        # are caught before they reach the DB.
        if self.source is UrlSource.SCAN and self.tool is None:
            raise ValueError("UrlFinding source=SCAN requires a non-None tool")
        if self.source is UrlSource.USER and self.tool is not None:
            raise ValueError("UrlFinding source=USER must have tool=None")
