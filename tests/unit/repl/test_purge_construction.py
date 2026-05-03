"""Tests for the construction-helper paths in :class:`PurgeCommand`.

Covers the per-helper service routing introduced in B6d. Each test
patches the application service classmethod so no real SQLite or
ChromaDB is touched.
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
    def test_returns_kb_from_cache_helper(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        sentinel_kb = MagicMock(name="finding_kb")
        with patch(
            "application.repl.commands.purge.get_or_build_knowledge_base",
            return_value=sentinel_kb,
        ) as mock_helper:
            result = cmd._get_knowledge_base()
        assert result is sentinel_kb
        mock_helper.assert_called_once_with(
            repl.knowledge_base_cache, _PROJECT, "/tmp/tally"
        )

    def test_raises_rag_unavailable_when_helper_returns_none(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        with patch(
            "application.repl.commands.purge.get_or_build_knowledge_base",
            return_value=None,
        ):
            with pytest.raises(RagUnavailable):
                cmd._get_knowledge_base()

    def test_cmd_purge_prints_rag_error_on_unavailable(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        with patch(
            "application.repl.commands.purge.get_or_build_knowledge_base",
            return_value=None,
        ):
            cmd.cmd_purge("purge", [])
        printed = [str(c) for c in repl.console.print.call_args_list]
        assert any("RAG error" in p for p in printed)


class TestPurgeCountChatSessions:
    def test_returns_session_count_via_chat_session_service(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        fake_sessions = [object(), object(), object()]
        sentinel_repo = MagicMock()
        sentinel_repo.list_for_project.return_value = fake_sessions
        sentinel_service = MagicMock(session_repo=sentinel_repo)
        with patch(
            "application.repl.commands.purge.ChatSessionService.for_project",
            return_value=sentinel_service,
        ) as mock_for_project:
            result = cmd._count_chat_sessions()
        assert result == 3
        mock_for_project.assert_called_once_with(repl.project_registry, _PROJECT_ID)
        sentinel_repo.list_for_project.assert_called_once_with(
            _PROJECT_ID, include_expired=True
        )

    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._count_chat_sessions() == 0


class TestPurgePurgeChat:
    def test_delegates_to_sealing_helper_with_service_session_repo(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        sentinel_repo = MagicMock(name="session_repo_port")
        sentinel_service = MagicMock(session_repo=sentinel_repo)
        with (
            patch(
                "application.repl.commands.purge.ChatSessionService.for_project",
                return_value=sentinel_service,
            ),
            patch(
                "application.repl.commands.purge.purge_chat_for_project",
                return_value=4,
            ) as mock_purge,
        ):
            result = cmd._purge_chat()
        assert result == 4
        mock_purge.assert_called_once_with(_PROJECT_ID, session_repo=sentinel_repo)

    def test_returns_zero_and_prints_warning_on_exception(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        with patch(
            "application.repl.commands.purge.ChatSessionService.for_project",
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
    def test_returns_count_via_findings_service(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        sentinel_service = MagicMock()
        sentinel_service.count_findings.return_value = 17
        with patch(
            "application.repl.commands.purge.FindingsService.for_project",
            return_value=sentinel_service,
        ):
            result = cmd._count_sqlite_findings(tools=["semgrep"])
        assert result == 17
        sentinel_service.count_findings.assert_called_once_with(tools=["semgrep"])

    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._count_sqlite_findings(tools=None) == 0


class TestPurgeCountUrlFindings:
    def test_returns_count_via_url_list_service(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        sentinel_service = MagicMock()
        sentinel_service.count_all_url_findings.return_value = 9
        with patch(
            "application.repl.commands.purge.UrlListService.for_project",
            return_value=sentinel_service,
        ):
            result = cmd._count_url_findings()
        assert result == 9
        sentinel_service.count_all_url_findings.assert_called_once_with()

    def test_returns_zero_when_resolve_returns_none(self) -> None:
        repl = _mock_repl()
        repl.project_registry.resolve_by_name.return_value = None
        cmd = PurgeCommand(repl)
        assert cmd._count_url_findings() == 0


class TestPurgeSqliteFullWipe:
    def test_full_wipe_calls_url_purge_then_findings_purge(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        findings_svc = MagicMock()
        url_svc = MagicMock()
        with (
            patch(
                "application.repl.commands.purge.FindingsService.for_project",
                return_value=findings_svc,
            ),
            patch(
                "application.repl.commands.purge.UrlListService.for_project",
                return_value=url_svc,
            ),
        ):
            cmd._purge_sqlite(tools=None)
        url_svc.purge_all_url_findings.assert_called_once_with()
        findings_svc.purge_all_findings_data.assert_called_once_with()
        findings_svc.delete_findings_for_tools.assert_not_called()
        url_svc.delete_url_findings_for_tools.assert_not_called()


class TestPurgeSqlitePerTool:
    def test_per_tool_calls_findings_delete_and_url_delete_for_url_tools(
        self,
    ) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        findings_svc = MagicMock()
        url_svc = MagicMock()
        with (
            patch(
                "application.repl.commands.purge.FindingsService.for_project",
                return_value=findings_svc,
            ),
            patch(
                "application.repl.commands.purge.UrlListService.for_project",
                return_value=url_svc,
            ),
        ):
            cmd._purge_sqlite(tools=["gitleaks", "katana"])
        findings_svc.delete_findings_for_tools.assert_called_once_with(
            ["gitleaks", "katana"]
        )
        url_svc.delete_url_findings_for_tools.assert_called_once_with(["katana"])
        findings_svc.purge_all_findings_data.assert_not_called()
        url_svc.purge_all_url_findings.assert_not_called()

    def test_per_tool_skips_url_delete_when_no_url_tools(self) -> None:
        repl = _mock_repl()
        cmd = PurgeCommand(repl)
        findings_svc = MagicMock()
        url_svc = MagicMock()
        with (
            patch(
                "application.repl.commands.purge.FindingsService.for_project",
                return_value=findings_svc,
            ),
            patch(
                "application.repl.commands.purge.UrlListService.for_project",
                return_value=url_svc,
            ),
        ):
            cmd._purge_sqlite(tools=["gitleaks", "semgrep"])
        findings_svc.delete_findings_for_tools.assert_called_once_with(
            ["gitleaks", "semgrep"]
        )
        url_svc.delete_url_findings_for_tools.assert_not_called()
