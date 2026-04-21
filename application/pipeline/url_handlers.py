"""URL discovery pipeline handlers.

Event chain
-----------
::

    ToolCompleted (katana/noir)
          │
    URLSourceEmitter.handle()
          │  dispatches
          ▼
    URLSourceChanged
          │
    URLDedupeHandler.handle()
          │  merges all OAS3 sources via URLMerger
          │  dispatches
          ▼
    URLsDeduped (carries ConversionOutputs bag)
          │
          ├─► URLSeedsHandler.handle()  →  writes endpoints/<repo>/merged_urls.txt
          │                                outputs.seeds_path set
          │
          └─► URLOS3Handler.handle()   →  writes endpoints/<repo>/merged_oas3.json
                                          outputs.oas3_path set
          │
    (bus.dispatch returns — both handlers have run)
          │
    URLDedupeHandler dispatches
          ▼
    URLsConverted
          │
    ConfigUpdateHandler.handle()
          │  persists seeds_path + oas3_path to project.json
          ▼
    (done)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from core.config.manager import ConfigManager
from domain.pipeline.events import EventBus, ToolCompleted
from domain.pipeline.url_events import (
    ConversionOutputs,
    URLsConverted,
    URLsDeduped,
    URLSourceChanged,
)
from infrastructure.tools.wrappers.utils.url_merge import URLMerger

logger = logging.getLogger(__name__)

_DISCOVERY_TOOLS: frozenset[str] = frozenset({"katana", "noir"})


class URLSourceEmitter:
    """Subscribes to ToolCompleted; emits URLSourceChanged for discovery tools.

    Only fires when the completed tool is Katana or Noir and the run
    succeeded.  Skips repos with no ``base_urls`` (no URL to join paths to).
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def handle(self, event: ToolCompleted) -> None:
        tool = (event.result.tool_name or "").lower()
        if tool not in _DISCOVERY_TOOLS:
            return
        if not event.result.success:
            return

        try:
            repos = ConfigManager(event.base_path).load_repositories(event.project_name)
        except Exception:
            logger.warning(
                "URLSourceEmitter: could not load repos for project %r",
                event.project_name,
            )
            return

        repo = next((r for r in repos if r.name == event.repo), None)
        if repo is None or not repo.base_urls:
            return

        self._bus.dispatch(
            URLSourceChanged(
                repo_name=repo.name,
                project_name=event.project_name,
                base_path=event.base_path,
                base_url=repo.base_urls[0],
                tool_name=tool,
            )
        )


class URLDedupeHandler:
    """Subscribes to URLSourceChanged; merges all URL sources, emits URLsDeduped.

    After ``bus.dispatch(URLsDeduped)`` returns (i.e. both
    ``URLSeedsHandler`` and ``URLOS3Handler`` have run), reads the populated
    ``ConversionOutputs`` bag and dispatches ``URLsConverted``.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def handle(self, event: URLSourceChanged) -> None:
        try:
            repos = ConfigManager(event.base_path).load_repositories(event.project_name)
        except Exception:
            logger.warning(
                "URLDedupeHandler: could not load repos for project %r",
                event.project_name,
            )
            return

        repo = next((r for r in repos if r.name == event.repo_name), None)
        user_oas3 = repo.oas3_path if repo is not None else ""

        merger = URLMerger(
            base_path=event.base_path,
            project_name=event.project_name,
            repo_name=event.repo_name,
            base_url=event.base_url,
            user_oas3_path=user_oas3,
        )
        urls = merger.merge()

        if not urls:
            logger.info(
                "URLDedupeHandler: no URLs for %s — skipping format generation",
                event.repo_name,
            )
            return

        outputs = ConversionOutputs()
        self._bus.dispatch(
            URLsDeduped(
                urls=urls,
                repo_name=event.repo_name,
                project_name=event.project_name,
                base_path=event.base_path,
                outputs=outputs,
            )
        )

        # Both format handlers have now run; outputs bag is populated.
        self._bus.dispatch(
            URLsConverted(
                repo_name=event.repo_name,
                project_name=event.project_name,
                base_path=event.base_path,
                seeds_path=outputs.seeds_path,
                oas3_path=outputs.oas3_path,
            )
        )


class URLSeedsHandler:
    """Subscribes to URLsDeduped; writes plain-text seeds file (one URL/line).

    Output: ``projects/<project>/endpoints/<repo>/merged_urls.txt``
    Consumed by: XSStrike (``--seeds``), DalFox (``file`` subcommand).
    """

    def handle(self, event: URLsDeduped) -> None:
        output_dir = (
            Path(event.base_path)
            / "projects"
            / event.project_name
            / "endpoints"
            / event.repo_name
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        seeds_path = output_dir / "merged_urls.txt"

        try:
            seeds_path.write_text("\n".join(event.urls) + "\n", encoding="utf-8")
            event.outputs.seeds_path = str(seeds_path)
            logger.info(
                "URLSeedsHandler: wrote %d URLs to %s",
                len(event.urls),
                seeds_path,
            )
        except OSError as exc:
            logger.error("URLSeedsHandler: failed to write seeds file: %s", exc)


class URLOS3Handler:
    """Subscribes to URLsDeduped; writes a merged OAS3 JSON document.

    Output: ``projects/<project>/endpoints/<repo>/merged_oas3.json``
    Consumed by: ZAP (``-openapifile``).

    The generated spec is minimal — one ``get`` operation per unique path —
    sufficient for ZAP to enumerate all discovered endpoints.
    """

    def handle(self, event: URLsDeduped) -> None:
        output_dir = (
            Path(event.base_path)
            / "projects"
            / event.project_name
            / "endpoints"
            / event.repo_name
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        oas3_file = output_dir / "merged_oas3.json"

        paths: dict[str, dict] = {}
        base_url = ""
        for url in event.urls:
            try:
                parsed = urlsplit(url)
                if not base_url and parsed.scheme and parsed.netloc:
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                path_key = parsed.path or "/"
            except Exception:
                path_key = "/"
            if path_key not in paths:
                paths[path_key] = {"get": {"responses": {"200": {"description": "OK"}}}}

        doc: dict = {
            "openapi": "3.0.0",
            "info": {"title": event.repo_name, "version": "0.0.0"},
            "servers": [{"url": base_url}] if base_url else [],
            "paths": paths,
        }

        try:
            oas3_file.write_text(json.dumps(doc, indent=2), encoding="utf-8")
            event.outputs.oas3_path = str(oas3_file)
            logger.info(
                "URLOS3Handler: wrote merged OAS3 with %d paths to %s",
                len(paths),
                oas3_file,
            )
        except OSError as exc:
            logger.error("URLOS3Handler: failed to write OAS3 file: %s", exc)


class ConfigUpdateHandler:
    """Subscribes to URLsConverted; persists artifact paths to project.json."""

    def handle(self, event: URLsConverted) -> None:
        try:
            manager = ConfigManager(event.base_path)
            repos = manager.load_repositories(event.project_name)
        except Exception as exc:
            logger.error("ConfigUpdateHandler: could not load repositories: %s", exc)
            return

        updated = []
        found = False
        for repo in repos:
            if repo.name == event.repo_name:
                repo = repo.model_copy(
                    update={
                        "merged_seeds_path": event.seeds_path,
                        "merged_oas3_path": event.oas3_path,
                    }
                )
                found = True
            updated.append(repo)

        if not found:
            logger.warning(
                "ConfigUpdateHandler: repo %r not found in project %r",
                event.repo_name,
                event.project_name,
            )
            return

        try:
            manager.save_repositories(event.project_name, updated)
        except Exception as exc:
            logger.error("ConfigUpdateHandler: save failed: %s", exc)


def regenerate_url_artifacts(
    base_path: str,
    project_name: str,
    repo_name: str,
    base_url: str,
    user_oas3_path: str = "",
) -> tuple[str, str]:
    """Merge URL sources and write seeds.txt + merged_oas3.json.

    Called directly from ``InteractiveProjectWizard`` when a user-provided
    endpoint file is saved, bypassing the EventBus (which is scan-time only).

    Returns:
        ``(seeds_path, oas3_path)`` — absolute paths to the written files,
        or empty strings if no URLs could be produced.
    """
    merger = URLMerger(
        base_path=base_path,
        project_name=project_name,
        repo_name=repo_name,
        base_url=base_url,
        user_oas3_path=user_oas3_path,
    )
    urls = merger.merge()

    if not urls:
        return "", ""

    outputs = ConversionOutputs()

    seeds_evt = URLsDeduped(
        urls=urls,
        repo_name=repo_name,
        project_name=project_name,
        base_path=base_path,
        outputs=outputs,
    )
    URLSeedsHandler().handle(seeds_evt)
    URLOS3Handler().handle(seeds_evt)

    return outputs.seeds_path, outputs.oas3_path
