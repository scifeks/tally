"""Regression tests: FullScan must update config.remaining_peers for each segment.

Without this, sub-strategies always see remaining_peers=0 → remaining_tools=0 →
"Approve all remaining?" never fires → auto_approve can never be set via the
prompt during a plain `scan` run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.tools.scan_types.full import FullScan
from domain.tools.scan_types.models import SEGMENT_ORDER, ScanTypeConfig


def _make_config(**overrides) -> ScanTypeConfig:
    defaults: dict = dict(
        project_name="proj",
        base_path="/tmp/proj",
        config_manager=MagicMock(),
        event_bus=MagicMock(),
        display=MagicMock(),
        run_id=None,
    )
    defaults.update(overrides)
    return ScanTypeConfig(**defaults)


def _make_resources(tool_names: list[str] | None = None) -> MagicMock:
    resources = MagicMock()
    tools = []
    for name in tool_names or []:
        t = MagicMock()
        t.name = name
        t.scan_segment = "sast"
        tools.append(t)
    resources.registry.get_all_tools.return_value = tools
    return resources


class TestFullScanRemainingPeers:
    def test_first_segment_sees_nonzero_remaining_peers(self) -> None:
        """First sub-strategy call must see remaining_peers > 0 when ≥2 segments."""
        config = _make_config()
        resources = _make_resources()

        captured: list[int] = []

        def _fake_execute(cfg: ScanTypeConfig, _res: object) -> MagicMock:
            captured.append(cfg.remaining_peers)
            return MagicMock(
                total_tools_run=0,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                findings_ingested=0,
                findings_by_tool={},
            )

        active = [s for s in SEGMENT_ORDER]
        assert len(active) >= 2, "Need ≥2 segments for this test to be meaningful"

        with (
            patch("application.tools.scan_types.full.NetworkSegmentScan") as MockNet,
            patch("application.tools.scan_types.full.RepoSegmentScan") as MockRepo,
        ):
            MockNet.return_value.execute.side_effect = _fake_execute
            MockRepo.return_value.execute.side_effect = _fake_execute

            FullScan().execute(config, resources)

        assert len(captured) == len(active)
        assert captured[0] > 0, (
            "First segment must have remaining_peers > 0 so 'Approve all remaining?' "
            "can fire"
        )

    def test_last_segment_sees_zero_remaining_peers(self) -> None:
        """Last sub-strategy call must see remaining_peers == 0."""
        config = _make_config()
        resources = _make_resources()

        captured: list[int] = []

        def _fake_execute(cfg: ScanTypeConfig, _res: object) -> MagicMock:
            captured.append(cfg.remaining_peers)
            return MagicMock(
                total_tools_run=0,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                findings_ingested=0,
                findings_by_tool={},
            )

        with (
            patch("application.tools.scan_types.full.NetworkSegmentScan") as MockNet,
            patch("application.tools.scan_types.full.RepoSegmentScan") as MockRepo,
        ):
            MockNet.return_value.execute.side_effect = _fake_execute
            MockRepo.return_value.execute.side_effect = _fake_execute

            FullScan().execute(config, resources)

        assert captured[-1] == 0, "Last segment must have remaining_peers == 0"

    def test_remaining_peers_decrements_each_segment(self) -> None:
        """remaining_peers must decrease by 1 for each successive segment."""
        config = _make_config()
        resources = _make_resources()

        captured: list[int] = []

        def _fake_execute(cfg: ScanTypeConfig, _res: object) -> MagicMock:
            captured.append(cfg.remaining_peers)
            return MagicMock(
                total_tools_run=0,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                findings_ingested=0,
                findings_by_tool={},
            )

        with (
            patch("application.tools.scan_types.full.NetworkSegmentScan") as MockNet,
            patch("application.tools.scan_types.full.RepoSegmentScan") as MockRepo,
        ):
            MockNet.return_value.execute.side_effect = _fake_execute
            MockRepo.return_value.execute.side_effect = _fake_execute

            FullScan().execute(config, resources)

        for i in range(len(captured) - 1):
            assert captured[i] == captured[i + 1] + 1, (
                f"remaining_peers should decrement by 1 each step: captured={captured}"
            )

    def test_exclude_segments_reduces_remaining_peers_count(self) -> None:
        """Excluding a segment should reduce the total so peers are still accurate."""
        config = _make_config()
        resources = _make_resources()

        captured: list[int] = []

        def _fake_execute(cfg: ScanTypeConfig, _res: object) -> MagicMock:
            captured.append(cfg.remaining_peers)
            return MagicMock(
                total_tools_run=0,
                total_tools_skipped=0,
                total_tools_failed=0,
                results=[],
                findings_ingested=0,
                findings_by_tool={},
            )

        excluded = ["network"]
        active = [s for s in SEGMENT_ORDER if s not in excluded]

        with patch("application.tools.scan_types.full.RepoSegmentScan") as MockRepo:
            MockRepo.return_value.execute.side_effect = _fake_execute
            FullScan(exclude_segments=excluded).execute(config, resources)

        assert len(captured) == len(active)
        assert captured[0] == len(active) - 1
        assert captured[-1] == 0
