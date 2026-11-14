"""Unit tests for shared triage batch creation."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.triage.batch_creator import create_triage_batches


class TestCreateTriageBatches:
    def _make_deps(
        self,
        combos: list[tuple[str, str, str]],
        findings_map: dict[tuple[str, str, str], list[dict]],
    ) -> tuple[MagicMock, MagicMock]:
        triage_repo = MagicMock()
        triage_repo.cancel_remaining.return_value = 0
        triage_repo.get_active_finding_combos.return_value = combos
        triage_repo.fetch_active_findings_for_batching.side_effect = (
            lambda run_id, tool, repo, seg: findings_map.get((tool, repo, seg), [])
        )
        triage_repo.create_batches.return_value = [(1, 2)]
        tool_registry = MagicMock()
        tool_registry.get_all_tools.return_value = []
        return triage_repo, tool_registry

    def test_creates_batches_for_combos(self) -> None:
        findings = [
            {"id": 1, "file": "a.py", "severity": "medium"},
            {"id": 2, "file": "a.py", "severity": "low"},
        ]
        repo, registry = self._make_deps(
            combos=[("semgrep", "myrepo", "sast")],
            findings_map={("semgrep", "myrepo", "sast"): findings},
        )
        result = create_triage_batches(
            run_id=10,
            triage_repo=repo,
            tool_registry=registry,
            max_findings_per_batch=4,
        )
        repo.cancel_remaining.assert_called_once_with(10)
        repo.create_batches.assert_called_once()
        assert result == [(1, 2)]

    def test_passes_skip_tools_to_repo(self) -> None:
        tool = MagicMock()
        tool.name = "skipme"
        tool.skip = True
        repo, registry = self._make_deps(combos=[], findings_map={})
        registry.get_all_tools.return_value = [tool]

        create_triage_batches(
            run_id=10,
            triage_repo=repo,
            tool_registry=registry,
            max_findings_per_batch=4,
        )

        skip_tools = repo.get_active_finding_combos.call_args[0][1]
        assert "skipme" in skip_tools

    def test_returns_empty_for_no_combos(self) -> None:
        repo, registry = self._make_deps(combos=[], findings_map={})
        result = create_triage_batches(
            run_id=10,
            triage_repo=repo,
            tool_registry=registry,
            max_findings_per_batch=4,
        )
        assert result == []
