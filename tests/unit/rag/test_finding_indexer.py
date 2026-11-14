"""Unit tests for FindingIndexer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.ports.vector_index import VectorIndexError
from application.rag.finding_indexer import FindingIndexer


def _row(
    *,
    finding_id: int,
    tool: str,
    profile: str,
    fingerprint: str,
    run_id: int = 10,
    severity: str = "high",
    segment: str = "secrets",
    status: str = "active",
) -> dict:
    return {
        "id": finding_id,
        "tool": tool,
        "profile": profile,
        "fingerprint": fingerprint,
        "run_id": run_id,
        "severity": severity,
        "segment": segment,
        "status": status,
    }


class TestIndexFindings:
    def test_empty_ids_does_not_touch_kb(self) -> None:
        repo = MagicMock()
        repo.get_by_ids.return_value = []
        kb = MagicMock()

        FindingIndexer(finding_repo=repo).index_findings(kb, ids=[])

        kb.add_findings.assert_not_called()

    def test_groups_by_tool_and_profile(self) -> None:
        repo = MagicMock()
        repo.get_by_ids.return_value = [
            _row(finding_id=1, tool="gitleaks", profile="main", fingerprint="fp1"),
            _row(finding_id=2, tool="gitleaks", profile="main", fingerprint="fp2"),
            _row(finding_id=3, tool="semgrep", profile="main", fingerprint="fp3"),
        ]
        kb = MagicMock()
        handler = MagicMock()
        handler.render.side_effect = lambda row: f"rendered-{row['id']}"

        with patch(
            "application.rag.finding_indexer.ToolHandlerFactory.load",
            return_value=handler,
        ):
            FindingIndexer(finding_repo=repo).index_findings(kb, ids=[1, 2, 3])

        assert kb.add_findings.call_count == 2

    def test_skips_group_when_handler_missing(self) -> None:
        repo = MagicMock()
        repo.get_by_ids.return_value = [
            _row(finding_id=1, tool="gitleaks", profile="main", fingerprint="fp1"),
            _row(
                finding_id=2,
                tool="unknown_tool",
                profile="main",
                fingerprint="fp2",
            ),
        ]
        kb = MagicMock()

        def loader(tool_name: str):
            if tool_name == "unknown_tool":
                return None
            h = MagicMock()
            h.render.side_effect = lambda row: f"rendered-{row['id']}"
            return h

        with patch(
            "application.rag.finding_indexer.ToolHandlerFactory.load",
            side_effect=loader,
        ):
            FindingIndexer(finding_repo=repo).index_findings(kb, ids=[1, 2])

        assert kb.add_findings.call_count == 1
        call = kb.add_findings.call_args
        assert call.kwargs["ids"] == ["fp1:main"]

    def test_deduplicates_by_doc_id_last_wins(self) -> None:
        repo = MagicMock()
        repo.get_by_ids.return_value = [
            _row(
                finding_id=1,
                tool="gitleaks",
                profile="main",
                fingerprint="fp1",
                run_id=1,
            ),
            _row(
                finding_id=2,
                tool="gitleaks",
                profile="main",
                fingerprint="fp1",
                run_id=2,
            ),
            _row(
                finding_id=3,
                tool="gitleaks",
                profile="main",
                fingerprint="fp2",
                run_id=3,
            ),
        ]
        kb = MagicMock()
        handler = MagicMock()
        handler.render.side_effect = lambda row: f"rendered-{row['id']}"

        with patch(
            "application.rag.finding_indexer.ToolHandlerFactory.load",
            return_value=handler,
        ):
            FindingIndexer(finding_repo=repo).index_findings(kb, ids=[1, 2, 3])

        call = kb.add_findings.call_args
        assert call.kwargs["ids"] == ["fp1:main", "fp2:main"]
        assert call.kwargs["metadatas"][0]["run_id"] == 2

    def test_swallows_vector_index_error(self) -> None:
        repo = MagicMock()
        repo.get_by_ids.return_value = [
            _row(finding_id=1, tool="gitleaks", profile="main", fingerprint="fp1"),
        ]
        kb = MagicMock()
        kb.add_findings.side_effect = VectorIndexError("boom")
        handler = MagicMock()
        handler.render.side_effect = lambda _row: "rendered"

        with patch(
            "application.rag.finding_indexer.ToolHandlerFactory.load",
            return_value=handler,
        ):
            FindingIndexer(finding_repo=repo).index_findings(kb, ids=[1])

    def test_lets_unexpected_exceptions_propagate(self) -> None:
        repo = MagicMock()
        repo.get_by_ids.side_effect = RuntimeError("bug")
        kb = MagicMock()

        with pytest.raises(RuntimeError):
            FindingIndexer(finding_repo=repo).index_findings(kb, ids=[1])


class TestRemoveFindings:
    def test_empty_rows_does_not_touch_kb(self) -> None:
        kb = MagicMock()

        FindingIndexer(finding_repo=MagicMock()).remove_findings(kb, rows=[])

        kb.remove_findings_by_id.assert_not_called()

    def test_forwards_doc_ids_to_kb(self) -> None:
        kb = MagicMock()
        rows = [
            {"fingerprint": "fp1", "profile": "main"},
            {"fingerprint": "fp2", "profile": "main"},
        ]

        FindingIndexer(finding_repo=MagicMock()).remove_findings(kb, rows=rows)

        kb.remove_findings_by_id.assert_called_once_with(["fp1:main", "fp2:main"])

    def test_swallows_vector_index_error_on_remove(self) -> None:
        kb = MagicMock()
        kb.remove_findings_by_id.side_effect = VectorIndexError("boom")

        FindingIndexer(finding_repo=MagicMock()).remove_findings(
            kb, rows=[{"fingerprint": "fp1", "profile": "main"}]
        )
