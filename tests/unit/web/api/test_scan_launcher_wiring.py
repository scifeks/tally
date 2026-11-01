"""Verify _build_background_launcher wires the scan event sink."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from web.api.scans import _build_background_launcher


@patch("web.api.scans.create_finding_repo")
@patch("web.api.scans.create_scan_repos")
@patch("web.api.scans.ConfigManager")
def test_build_background_launcher_passes_sink_and_phase_repo(
    mock_cm: MagicMock,
    mock_scan_repos: MagicMock,
    mock_finding_repo: MagicMock,
) -> None:
    mock_scan_repos.return_value = (MagicMock(), None, None, None)
    mock_finding_repo.return_value = MagicMock()
    mock_cm.return_value.global_config = MagicMock()

    request = MagicMock()
    request.app.state.base_path = "/data/tally"
    request.app.state.event_bus = MagicMock()

    paths = MagicMock()
    paths.findings_db = "/tmp/test.db"

    launcher = _build_background_launcher(request, paths)

    assert launcher._scan_event_sink is not None
    assert launcher._scan_phase_repo is not None
