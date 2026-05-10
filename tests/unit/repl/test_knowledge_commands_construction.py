"""Tests for REPL knowledge_base_cache attribute and KnowledgeCommands
construction-helper paths."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

import pytest  # noqa: E402

from application.chat.stream_composer import (  # noqa: E402
    RagUnavailable,
)
from application.repl.commands.knowledge_commands import (  # noqa: E402
    KnowledgeCommands,
)
from domain.projects.entry import ProjectRow  # noqa: E402
from factories.persistence import ProjectNotFound  # noqa: E402

_PROJECT = "testproj"


def _mock_repl(active_project: str | None = _PROJECT) -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/tally"
    repl.knowledge_base_cache = {}
    return repl


class TestKnowledgeCommandsResolveProjectId:
    def test_raises_value_error_when_project_missing(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        kc = KnowledgeCommands(repl)
        with pytest.raises(ValueError, match="project not found"):
            kc._resolve_project_id()


class TestKnowledgeCommandsGetFindingRepo:
    def test_returns_none_and_prints_on_project_not_found(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = ProjectRow(
            id=7,
            name=_PROJECT,
            path="/tmp/p",
            created_at="2026-05-03T00:00:00Z",
        )
        kc = KnowledgeCommands(repl)
        with patch(
            "application.repl.commands.knowledge_commands.create_findings_service",
            side_effect=ProjectNotFound("project 7 not found"),
        ):
            result = kc._get_finding_repo()
        assert result is None
        printed = [str(c) for c in repl.console.print.call_args_list]
        assert any("Project error" in p for p in printed)

    def test_returns_none_and_prints_on_resolve_value_error(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        kc = KnowledgeCommands(repl)
        result = kc._get_finding_repo()
        assert result is None
        printed = [str(c) for c in repl.console.print.call_args_list]
        assert any("Project error" in p for p in printed)


class TestKnowledgeCommandsGetKnowledgeBase:
    def test_raises_rag_unavailable_when_helper_returns_none(
        self,
    ) -> None:
        repl = _mock_repl()
        kc = KnowledgeCommands(repl)
        with patch(
            "application.repl.commands.knowledge_commands.get_or_build_knowledge_base",
            return_value=None,
        ):
            with pytest.raises(RagUnavailable):
                kc._get_knowledge_base()
