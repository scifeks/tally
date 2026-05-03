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
from application.findings.findings_service import (  # noqa: E402
    ProjectNotFound,
)
from application.repl.commands.knowledge_commands import (  # noqa: E402
    KnowledgeCommands,
)
from domain.projects.entry import ProjectRow  # noqa: E402

_PROJECT = "testproj"


def _mock_repl(active_project: str | None = _PROJECT) -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/tally"
    repl.knowledge_base_cache = {}
    return repl


class TestREPLKnowledgeBaseCacheAttribute:
    def test_repl_init_starts_with_empty_cache(self) -> None:
        from application.repl.interface import REPL

        with (
            patch("application.repl.interface.discover_tools"),
            patch("infrastructure.store.project_registry.ProjectRegistryRepository"),
            patch("application.repl.interface.ProjectRegistryService"),
            patch("application.repl.interface.ConfigManager"),
            patch("application.repl.interface.ProjectManager"),
            patch("application.repl.interface.InteractiveProjectWizard"),
            patch("infrastructure.web_ui.runner.WebUiRunner"),
            patch("application.repl.help_renderer.HelpRenderer"),
        ):
            repl = REPL(base_path="/tmp/tally")
            assert repl.knowledge_base_cache == {}


class TestKnowledgeCommandsResolveProjectId:
    def test_returns_id_when_registry_has_project(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = ProjectRow(
            id=42,
            name=_PROJECT,
            path="/tmp/p",
            created_at="2026-05-03T00:00:00Z",
        )
        kc = KnowledgeCommands(repl)
        assert kc._resolve_project_id() == 42

    def test_raises_value_error_when_project_missing(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        kc = KnowledgeCommands(repl)
        with pytest.raises(ValueError, match="project not found"):
            kc._resolve_project_id()


class TestKnowledgeCommandsGetFindingRepo:
    def test_returns_finding_repo_from_findings_service(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = ProjectRow(
            id=7,
            name=_PROJECT,
            path="/tmp/p",
            created_at="2026-05-03T00:00:00Z",
        )
        kc = KnowledgeCommands(repl)
        sentinel_repo = MagicMock(name="finding_repo_port")
        sentinel_service = MagicMock(finding_repo=sentinel_repo)
        with patch(
            "application.repl.commands.knowledge_commands.FindingsService.for_project",
            return_value=sentinel_service,
        ) as mock_for_project:
            result = kc._get_finding_repo()
        assert result is sentinel_repo
        mock_for_project.assert_called_once_with(repl.project_registry, 7)

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
            "application.repl.commands.knowledge_commands.FindingsService.for_project",
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
    def test_returns_kb_from_cache_helper(self) -> None:
        repl = _mock_repl()
        kc = KnowledgeCommands(repl)
        sentinel_kb = MagicMock(name="finding_kb")
        with patch(
            "application.repl.commands.knowledge_commands.get_or_build_knowledge_base",
            return_value=sentinel_kb,
        ) as mock_helper:
            result = kc._get_knowledge_base()
        assert result is sentinel_kb
        mock_helper.assert_called_once_with(
            repl.knowledge_base_cache, _PROJECT, "/tmp/tally"
        )

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


class TestCmdChatAndStatsRagUnavailable:
    def test_cmd_chat_prints_rag_error_on_unavailable(self) -> None:
        repl = _mock_repl()
        kc = KnowledgeCommands(repl)
        with patch(
            "application.repl.commands.knowledge_commands.get_or_build_knowledge_base",
            return_value=None,
        ):
            kc.cmd_chat("chat", ["hello"])
        printed = [str(c) for c in repl.console.print.call_args_list]
        assert any("RAG error" in p for p in printed)

    def test_cmd_stats_prints_rag_error_on_unavailable(self) -> None:
        repl = _mock_repl()
        kc = KnowledgeCommands(repl)
        with patch(
            "application.repl.commands.knowledge_commands.get_or_build_knowledge_base",
            return_value=None,
        ):
            kc.cmd_stats("stats", [])
        printed = [str(c) for c in repl.console.print.call_args_list]
        assert any("RAG error" in p for p in printed)
