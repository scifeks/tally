"""Chooses what a sync sends: one batch per repo and tool."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from application.mcp.duplicate_grouping import (
    GroupableFinding,
    group_duplicate_candidates,
)
from application.ports.export import SyncBatch

if TYPE_CHECKING:
    from application.ports.export import SyncRepo
    from application.ports.finding_repository import FindingRepositoryPort
    from application.ports.run_repository import RunRepositoryPort
    from domain.findings.entry import Finding

# A missing finding from these tools is not evidence it is gone: they are
# hand-fed, stochastic or scoped differently on every scan.
ACCUMULATING_TOOLS = frozenset({"manual", "claudecode", "opencode", "burp"})
_PROXIMITY_TOOLS = frozenset({"claudecode", "opencode"})
_PROXIMITY_LINES = 10


class SyncSelector:
    def __init__(
        self,
        finding_repo: FindingRepositoryPort,
        run_repo: RunRepositoryPort,
        repos: list[SyncRepo],
    ) -> None:
        self._finding_repo = finding_repo
        self._run_repo = run_repo
        self._services_by_repo = {repo.id: repo.services for repo in repos}

    def select(self, run_id: int | None = None) -> list[SyncBatch]:
        """Return the project's current state, narrowed to a run if given."""
        all_findings = self._finding_repo.get_all_findings()
        grouped: dict[tuple[int, str], list[Finding]] = defaultdict(list)
        for finding in all_findings:
            repo_id = finding.repo_id
            if repo_id is None or repo_id not in self._services_by_repo:
                continue
            if not finding.tool:
                continue
            grouped[(repo_id, finding.tool)].append(finding)

        batches: list[SyncBatch] = []
        for (repo_id, tool), findings in sorted(grouped.items()):
            if tool in ACCUMULATING_TOOLS:
                chosen: list[Finding] | None = _collapse(tool, findings)
            else:
                chosen = self._latest_scan(repo_id, tool, findings)
            if chosen is None:
                continue
            ordered = tuple(sorted(chosen, key=lambda f: f.id))
            batches.append(SyncBatch(repo_id, tool, ordered))

        if run_id is None:
            return batches
        touched = self._touched(run_id, all_findings)
        return [b for b in batches if (b.repo_id, b.tool) in touched]

    def _latest_scan(
        self, repo_id: int, tool: str, findings: list[Finding]
    ) -> list[Finding] | None:
        chosen: list[Finding] = []
        scanned = False
        for service in self._services_by_repo[repo_id]:
            latest = self._run_repo.latest_done_run_id(
                repo_id=repo_id, service=service, tool=tool
            )
            if latest is None:
                continue
            scanned = True
            from_run = [
                f for f in findings if f.run_id == latest and f.service == service
            ]
            # A tool that started twice in one run stored its findings twice.
            chosen.extend(_newest_per_fingerprint(from_run))
        return chosen if scanned else None

    def _touched(
        self, run_id: int, all_findings: list[Finding]
    ) -> set[tuple[int | None, str]]:
        touched = set(self._run_repo.list_repo_tool_pairs(run_id))
        for finding in all_findings:
            if finding.run_id == run_id and finding.tool:
                touched.add((finding.repo_id, finding.tool))
        return touched


def _newest_per_fingerprint(findings: list[Finding]) -> list[Finding]:
    newest: dict[str, Finding] = {}
    unkeyed: list[Finding] = []
    for finding in findings:
        if finding.fingerprint is None:
            unkeyed.append(finding)
            continue
        current = newest.get(finding.fingerprint)
        if current is None or finding.id > current.id:
            newest[finding.fingerprint] = finding
    return [*newest.values(), *unkeyed]


def _collapse(tool: str, findings: list[Finding]) -> list[Finding]:
    kept = _newest_per_fingerprint(findings)
    if tool not in _PROXIMITY_TOOLS:
        return kept

    groups = group_duplicate_candidates(
        [
            GroupableFinding(
                id=f.id,
                file=f.file,
                rule_id=f.rule_id,
                line_start=f.meta.get("line_number"),
                line_end=f.meta.get("line_end") or f.meta.get("line_number"),
            )
            for f in kept
        ],
        proximity=_PROXIMITY_LINES,
    )
    # Groups come back sorted ascending, so the last ID is the newest copy.
    dropped = {finding_id for group in groups for finding_id in group[:-1]}
    return [f for f in kept if f.id not in dropped]
