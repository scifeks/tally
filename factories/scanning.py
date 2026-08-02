"""Scanning factory functions for composition root wiring."""

from __future__ import annotations

from application.ports.git_diff import GitDiffPort
from application.ports.subprocess_runner import SubprocessRunnerPort
from application.tools.scan_service import ScanService
from infrastructure.tools.runner import SubprocessRunner
from infrastructure.vcs.git_diff_adapter import GitDiffAdapter


def create_subprocess_runner() -> SubprocessRunnerPort:
    """Construct a subprocess runner."""
    return SubprocessRunner()


def create_git_diff() -> GitDiffPort:
    """Construct a git diff adapter."""
    return GitDiffAdapter(SubprocessRunner())


_SERVICE: ScanService | None = None


def get_scan_service() -> ScanService:
    """Return the process-shared ScanService singleton."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = ScanService(
            subprocess_runner=SubprocessRunner(),
        )
    return _SERVICE
