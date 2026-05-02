"""Persistence port for the url_findings table.

Read methods return UrlFinding. The port boundary stays free of
infrastructure types.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool


class UrlFindingRepositoryPort(Protocol):
    def insert_many(self, findings: Iterable[UrlFinding]) -> int: ...
    def delete_for_repo_and_tool(self, repo_id: int, tool: UrlTool) -> int: ...
    def delete_for_user_file(self, repo_id: int, file_path: str) -> int: ...
    def delete_for_repo(self, repo_id: int) -> int: ...
    def delete_all(self) -> int: ...
    def list_for_repo(
        self, repo_id: int, *, source: UrlSource | None = None
    ) -> list[UrlFinding]: ...
    def list_paginated(
        self,
        *,
        repo_id: list[int] | None = None,
        source: UrlSource | None = None,
        tool: UrlTool | None = None,
        method: list[str] | None = None,
        protocol: list[str] | None = None,
        host: list[str] | None = None,
        port: list[int] | None = None,
        path: list[str] | None = None,
        search: str | None = None,
        sort: str = "host",
        order: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[UrlFinding], int]: ...
    def filter_options(self, filters: dict[str, Any]) -> dict: ...
    def count_active(self) -> int: ...
