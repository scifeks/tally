"""Ports (Protocols) for the URL inventory layer (Phase 9)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.config.schemas import Repository
    from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool


class UrlFindingRepositoryPort(Protocol):
    """The persistence port for ``url_findings`` rows.

    Concrete implementation lives in
    ``infrastructure.store.repositories.url_findings``.
    """

    def insert_many(self, findings: Iterable[UrlFinding]) -> int: ...
    def delete_for_repo_and_tool(self, repo_id: int, tool: UrlTool) -> int: ...
    def delete_for_user_file(self, repo_id: int, file_path: str) -> int: ...
    def delete_for_repo(self, repo_id: int) -> int: ...
    def list_for_repo(
        self, repo_id: int, *, source: UrlSource | None = None
    ) -> list[UrlFinding]: ...
    def list_paginated(
        self,
        *,
        repo_id: int | None = None,
        source: UrlSource | None = None,
        tool: UrlTool | None = None,
        search: str | None = None,
        method: str | None = None,
        sort: str = "host",
        order: str = "asc",
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[UrlFinding], int]: ...


@dataclass(frozen=True)
class UrlProviderContext:
    """State a URL provider needs to emit rows for one repo on one run.

    For SCAN-source providers (Katana, Noir), ``run_id`` is set; for
    USER-source providers, ``run_id`` is None.
    """

    repo: Repository
    repo_id: int
    base_path: str
    project_name: str
    run_id: int | None = None


@runtime_checkable
class UrlListProvider(Protocol):
    """A producer of ``UrlFinding`` rows for a given (repo, tool) pair.

    Concrete implementations: KatanaProvider, NoirProvider, UserFileProvider
    (Step 4 of the Phase 9 plan).
    """

    source: UrlSource
    tool: UrlTool | None

    def provide(self, ctx: UrlProviderContext) -> Iterable[UrlFinding]: ...
