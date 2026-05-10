"""Tests for the construction-helper paths in PurgeCommand.

Each test patches the application service classmethod so no real SQLite
or ChromaDB is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

import pytest  # noqa: E402

from application.chat.stream_composer import RagUnavailable  # noqa: E402
from application.repl.commands.purge import PurgeCommand  # noqa: E402
from domain.projects.entry import ProjectRow  # noqa: E402

_PROJECT = "testproj"
_PROJECT_ID = 7


def _mock_repl(active_project: str | None = _PROJECT) -> MagicMock:
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = "/tmp/tally"
    repl.knowledge_base_cache = {}
    if active_project is not None:
        repl.project_registry.resolve_by_name.return_value = ProjectRow(
            id=_PROJECT_ID,
            name=active_project,
            path="/tmp/tally/projects/" + active_project,
            created_at="2026-05-03T00:00:00Z",
        )
    return repl


class TestPurgeGetKnowledgeBase:
    def test_raises_rag_unavailable_when_helper_returns_none(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        with patch(
            "application.repl.commands.purge.get_or_build_knowledge_base",
            return_value=None,
        ):
            with pytest.raises(RagUnavailable):
                cmd._get_knowledge_base()


class TestPurgeCountChatSessions:
    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._count_chat_sessions() == 0


class TestPurgePurgeChat:
    def test_purge_chat_returns_count(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        sentinel_repo = MagicMock(name="session_repo_port")
        sentinel_service = MagicMock(session_repo=sentinel_repo)
        with (
            patch(
                "application.repl.commands.purge.create_chat_session_service",
                return_value=sentinel_service,
            ),
            patch(
                "application.repl.commands.purge.purge_chat_for_project",
                return_value=4,
            ),
        ):
            result = cmd._purge_chat()
        assert result == 4

    def test_returns_zero_and_prints_warning_on_exception(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        with patch(
            "application.repl.commands.purge.create_chat_session_service",
            side_effect=RuntimeError("boom"),
        ):
            result = cmd._purge_chat()
        assert result == 0
        printed = [str(c) for c in repl.console.print.call_args_list]
        assert any("Chat purge warning" in p for p in printed)

    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._purge_chat() == 0


class TestPurgeCountSqliteFindings:
    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._count_sqlite_findings(tools=None) == 0


class TestPurgeCountUrlFindings:
    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._count_url_findings() == 0


class TestPurgeSqliteFullWipe:
    def test_full_wipe_purges_all_findings(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        findings_svc = MagicMock()
        url_svc = MagicMock()
        with (
            patch(
                "application.repl.commands.purge.create_findings_service",
                return_value=findings_svc,
            ),
            patch(
                "application.repl.commands.purge.create_url_list_service",
                return_value=url_svc,
            ),
        ):
            cmd._purge_sqlite(tools=None)
        assert url_svc.purge_all_url_findings.called
        assert findings_svc.purge_all_findings_data.called


class TestPurgeSqlitePerTool:
    def test_per_tool_deletes_findings_for_selected_tools(
        self,
    ) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        findings_svc = MagicMock()
        url_svc = MagicMock()
        with (
            patch(
                "application.repl.commands.purge.create_findings_service",
                return_value=findings_svc,
            ),
            patch(
                "application.repl.commands.purge.create_url_list_service",
                return_value=url_svc,
            ),
        ):
            cmd._purge_sqlite(tools=["gitleaks", "katana"])
        assert findings_svc.delete_findings_for_tools.called
        assert url_svc.delete_url_findings_for_tools.called

    def test_per_tool_handles_non_url_tools(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        findings_svc = MagicMock()
        url_svc = MagicMock()
        with (
            patch(
                "application.repl.commands.purge.create_findings_service",
                return_value=findings_svc,
            ),
            patch(
                "application.repl.commands.purge.create_url_list_service",
                return_value=url_svc,
            ),
        ):
            cmd._purge_sqlite(tools=["gitleaks", "semgrep"])
        assert findings_svc.delete_findings_for_tools.called
