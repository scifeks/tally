"""Provider seam types for the URL inventory layer (Phase 9).

The ``UrlFindingRepositoryPort`` persistence port lived here originally
and was relocated to ``application/ports/url_finding_repository.py`` in
Slice 9 (A5e) so every persistence port shares one folder.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.config.schemas import Repository
    from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool


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
