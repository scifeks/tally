"""Unit tests for the rules that decide what a sync sends."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.export.selection import SyncSelector
from application.ports.export import SyncRepo
from domain.findings.entry import Finding

Done = dict[tuple[int, str | None, str], int]
Selected = dict[tuple[int, str], list[int]]

_ONE_SERVICE = [SyncRepo(1, ("default",))]
_TWO_SERVICES = [SyncRepo(1, ("api", "web"))]


def _finding(
    finding_id: int,
    tool: str,
    run_id: int | None,
    *,
    service: str | None = "default",
    repo_id: int | None = 1,
    fingerprint: str | None = None,
    file: str | None = None,
    rule_id: str | None = None,
    line: int | None = None,
) -> Finding:
    return Finding(
        id=finding_id,
        fingerprint=fingerprint or f"fp-{finding_id}",
        run_id=run_id,
        tool=tool,
        domain="code",
        segment="sast",
        file=file,
        rule_id=rule_id,
        meta={} if line is None else {"line_number": line},
        repo_id=repo_id,
        service=service,
    )


def _select(
    findings: list[Finding],
    done: Done,
    repos: list[SyncRepo],
    *,
    pairs: list[tuple[int | None, str]] | None = None,
    run_id: int | None = None,
) -> tuple[Selected, MagicMock]:
    finding_repo = MagicMock()
    finding_repo.get_all_findings.return_value = findings
    run_repo = MagicMock()
    run_repo.latest_done_run_id.side_effect = lambda *, repo_id, service, tool: (
        done.get((repo_id, service, tool))
    )
    run_repo.list_repo_tool_pairs.return_value = pairs or []
    batches = SyncSelector(finding_repo, run_repo, repos).select(run_id)
    selected = {(b.repo_id, b.tool): [f.id for f in b.findings] for b in batches}
    return selected, run_repo


class TestSyncSelector:
    @pytest.mark.parametrize(
        ("findings", "done", "repos", "expected"),
        [
            pytest.param(
                [_finding(1, "semgrep", 1), _finding(2, "semgrep", 2)],
                {(1, "default", "semgrep"): 2},
                _ONE_SERVICE,
                {(1, "semgrep"): [2]},
                id="newest_done_run_is_chosen",
            ),
            pytest.param(
                [_finding(1, "semgrep", 1), _finding(2, "semgrep", 2)],
                {(1, "default", "semgrep"): 1},
                _ONE_SERVICE,
                {(1, "semgrep"): [1]},
                id="newer_run_that_did_not_finish_is_passed_over",
            ),
            pytest.param(
                [_finding(1, "semgrep", 1)],
                {(1, "default", "semgrep"): 3},
                _ONE_SERVICE,
                {(1, "semgrep"): []},
                id="clean_newer_run_yields_an_empty_batch",
            ),
            pytest.param(
                [_finding(1, "semgrep", 1)],
                {},
                _ONE_SERVICE,
                {},
                id="tool_never_done_yields_no_batch",
            ),
            pytest.param(
                [
                    _finding(1, "semgrep", 1, service="api"),
                    _finding(2, "semgrep", 2, service="api"),
                    _finding(3, "semgrep", 1, service="web"),
                ],
                {(1, "api", "semgrep"): 2, (1, "web", "semgrep"): 1},
                _TWO_SERVICES,
                {(1, "semgrep"): [2, 3]},
                id="each_service_uses_its_own_newest_run",
            ),
            pytest.param(
                [
                    _finding(1, "semgrep", 1, service="api", fingerprint="same"),
                    _finding(2, "semgrep", 1, service="api", fingerprint="same"),
                    _finding(3, "semgrep", 1, service="web", fingerprint="same"),
                ],
                {(1, "api", "semgrep"): 1, (1, "web", "semgrep"): 1},
                _TWO_SERVICES,
                {(1, "semgrep"): [2, 3]},
                id="repeat_in_one_service_collapses_but_not_across_services",
            ),
            pytest.param(
                [
                    _finding(1, "semgrep", 1, service="api"),
                    _finding(2, "semgrep", 1, service="old"),
                ],
                {(1, "api", "semgrep"): 1, (1, "old", "semgrep"): 1},
                [SyncRepo(1, ("api",))],
                {(1, "semgrep"): [1]},
                id="removed_service_is_left_out",
            ),
            pytest.param(
                [
                    _finding(1, "semgrep", 1, repo_id=9),
                    _finding(2, "semgrep", 1, repo_id=None),
                ],
                {(9, "default", "semgrep"): 1},
                _ONE_SERVICE,
                {},
                id="removed_repo_and_missing_repo_yield_nothing",
            ),
        ],
    )
    def test_scanner_tool(
        self,
        findings: list[Finding],
        done: Done,
        repos: list[SyncRepo],
        expected: Selected,
    ) -> None:
        selected, _ = _select(findings, done, repos)

        assert selected == expected

    def test_accumulating_tool_sends_every_run_and_ignores_run_records(self) -> None:
        findings = [
            _finding(1, "manual", None, service=None),
            _finding(2, "manual", None, service=None),
            _finding(3, "burp", 4, service=None),
            _finding(4, "burp", 9, service=None),
        ]

        selected, run_repo = _select(findings, {}, _ONE_SERVICE)

        assert selected == {(1, "burp"): [3, 4], (1, "manual"): [1, 2]}
        run_repo.latest_done_run_id.assert_not_called()

    @pytest.mark.parametrize("tool", ["claudecode", "manual"])
    def test_same_fingerprint_keeps_only_the_newest_copy(self, tool: str) -> None:
        findings = [
            _finding(1, tool, 1, service=None, fingerprint="same"),
            _finding(5, tool, 2, service=None, fingerprint="same"),
            _finding(3, tool, 2, service=None, fingerprint="other"),
        ]

        selected, _ = _select(findings, {}, _ONE_SERVICE)

        assert selected == {(1, tool): [3, 5]}

    @pytest.mark.parametrize(
        ("tool", "second_line", "expected_ids"),
        [
            ("claudecode", 18, [2]),
            ("opencode", 18, [2]),
            ("claudecode", 20, [2]),
            ("claudecode", 21, [1, 2]),
            ("claudecode", 40, [1, 2]),
            ("manual", 18, [1, 2]),
            ("burp", 18, [1, 2]),
        ],
    )
    def test_ten_line_rule_applies_only_to_llm_scanners(
        self, tool: str, second_line: int, expected_ids: list[int]
    ) -> None:
        findings = [
            _finding(
                1, tool, 1, service=None, file="/a.py", rule_id="xss.stored", line=10
            ),
            _finding(
                2,
                tool,
                2,
                service=None,
                file="/a.py",
                rule_id="xss.stored",
                line=second_line,
            ),
        ]

        selected, _ = _select(findings, {}, _ONE_SERVICE)

        assert selected == {(1, tool): expected_ids}

    def test_run_narrows_the_pairs_but_sends_their_current_state(self) -> None:
        findings = [
            _finding(1, "semgrep", 1),
            _finding(3, "gitleaks", 1),
            _finding(4, "claudecode", 2, service=None),
            _finding(5, "claudecode", 3, service=None),
        ]
        done: Done = {(1, "default", "semgrep"): 3, (1, "default", "gitleaks"): 1}

        selected, _ = _select(
            findings,
            done,
            _ONE_SERVICE,
            pairs=[(1, "semgrep"), (None, "burp")],
            run_id=2,
        )

        # semgrep has no finding in run 2, so only its run row selects the batch.
        assert selected == {(1, "claudecode"): [4, 5], (1, "semgrep"): []}
