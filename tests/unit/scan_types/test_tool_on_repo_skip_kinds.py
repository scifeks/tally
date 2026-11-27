"""Tests for the skip kind and service ToolOnRepoScan reports."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.models import ScanTypeConfig
from application.tools.scan_types.tool_on_repo import ToolOnRepoScan
from domain.pipeline import scan_events as se
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.scan_types.resources import IExecutionResources


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[se.ScanEvent] = []

    def emit(self, event: se.ScanEvent) -> None:
        self.events.append(event)


def _service(base_urls: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        name="api",
        base_urls=base_urls,
        languages=["php"],
        relative_path="",
        docker_path="",
        container_name="",
        crawl_enabled=True,
    )


def _run(
    *,
    tool_config: object | None,
    available: bool,
    requires_base_urls: bool,
    base_urls: list[str],
) -> se.ToolSkipped:
    repo = SimpleNamespace(
        id=1, name="shop", path="/src/shop", services=[_service(base_urls)]
    )
    repo_repo = MagicMock()
    repo_repo.list_active.return_value = [repo]
    tool = MagicMock()
    tool.check_available.return_value = available
    tool.requires_base_urls = requires_base_urls
    tool.scan_segment = "web"
    registry = MagicMock()
    registry.get_tool_config.return_value = tool_config
    factory = MagicMock()
    factory.create.return_value = tool
    sink = _RecordingSink()
    resources = SimpleNamespace(
        registry=registry,
        factory=factory,
        executor=MagicMock(),
        event_bus=MagicMock(),
        display=MagicMock(),
        event_sink=sink,
    )
    config = ScanTypeConfig(
        project_name="proj",
        base_path="/tmp/proj",
        tool_config=ToolExecutionConfig(noir_provider=None),
        run_id=1,
        prompt=MagicMock(),
        repo_repo=repo_repo,
    )
    with patch(
        "application.tools.scan_types.tool_on_repo.noir_skip_reason",
        return_value=None,
    ):
        ToolOnRepoScan("zap", "shop").execute(
            config, cast(IExecutionResources, resources)
        )
    skipped = [e for e in sink.events if isinstance(e, se.ToolSkipped)]
    assert len(skipped) == 1
    return skipped[0]


class TestToolOnRepoSkipKinds:
    @pytest.mark.parametrize(
        ("tool_config", "available", "requires_base_urls", "base_urls", "kind"),
        [
            pytest.param(
                None, True, False, [], se.SKIP_COULD_NOT_RUN, id="not-registered"
            ),
            pytest.param(
                object(), False, False, [], se.SKIP_COULD_NOT_RUN, id="not-installed"
            ),
            pytest.param(
                object(), True, True, [], se.SKIP_NOT_APPLICABLE, id="no-base-urls"
            ),
        ],
    )
    def test_skip_carries_kind_and_service(
        self,
        tool_config: object | None,
        available: bool,
        requires_base_urls: bool,
        base_urls: list[str],
        kind: str,
    ) -> None:
        skipped = _run(
            tool_config=tool_config,
            available=available,
            requires_base_urls=requires_base_urls,
            base_urls=base_urls,
        )
        assert (skipped.kind, skipped.service) == (kind, "api")
