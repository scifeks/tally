"""Tests for CLI scan and triage fixes.

Covers interactive triage printing mcp_bearer_token, interactive scan
rejecting background-only flags, resume failure preserving run status,
resume defaulting to the run's original mode, and error text using
--billing-method.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.cli.commands.scan import (  # noqa: E402
    _cmd_scan_background,
    _cmd_scan_resume,
    _schedule_scan_launch,
)
from application.cli.commands.triage import (  # noqa: E402
    _cmd_triage_resume,
    _cmd_triage_with_mode,
    _print_interactive_triage_info,
)
from application.cli.exit_codes import (  # noqa: E402
    GENERAL_ERROR,
    INVALID_ARGS,
    SUCCESS,
)

# -- Helpers ------------------------------------------------------------------


def _make_args(**overrides: object) -> Namespace:
    """Build a Namespace with sane defaults for scan CLI args."""
    defaults = {
        "project": "testproj",
        "interaction_mode": None,
        "billing_method": None,
        "api_key_override": None,
        "only": None,
        "exclude": None,
        "resume": None,
        "list_skills": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _make_triage_args(**overrides: object) -> Namespace:
    """Build a Namespace with sane defaults for triage CLI args."""
    defaults = {
        "project": "testproj",
        "interaction_mode": None,
        "billing_method": None,
        "api_key_override": None,
        "resume": None,
        "rebuild_container": False,
        "batch": False,
        "dry_run": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def _stub_project_registry() -> MagicMock:
    registry = MagicMock()
    row = MagicMock()
    row.name = "testproj"
    row.id = 1
    row.archived_at = None
    registry.resolve_by_name.return_value = row
    return registry


def _make_handle(result_dict: dict) -> MagicMock:
    future: Future[dict] = Future()
    future.set_result(result_dict)
    handle = MagicMock()
    handle.result = future
    handle.scan_run_id = 42
    return handle


# -- Interactive triage prints bearer token -----------------------------------


class TestInteractiveTriagePrintsBearerToken:
    """_print_interactive_triage_info must print both mcp_url and mcp_bearer_token."""

    def test_prints_bearer_token(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_cfg = MagicMock()
        mock_cfg.global_config.mcp.host = "localhost"
        mock_cfg.global_config.mcp.port = 8080

        with (
            patch(
                "application.cli.commands.triage.mint_bearer_token",
                return_value="test-token-abc",
            ),
            patch(
                "application.cli.commands.triage.ConfigManager",
                return_value=mock_cfg,
            ),
        ):
            _print_interactive_triage_info("/app", scan_run_id=99)

        out = capsys.readouterr().out
        assert "mcp_url:" in out
        assert "mcp_bearer_token:" in out
        assert "test-token-abc" in out
        assert "scan_run_id:" in out

    def test_triage_with_mode_interactive_prints_token(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """End-to-end: _cmd_triage_with_mode in interactive mode prints the token."""
        service = MagicMock()
        handle = _make_handle(
            {
                "sessions_run": 1,
                "success": 1,
                "failed": 0,
                "incomplete": 0,
                "status": "completed",
            }
        )
        service.start_triage.return_value = handle

        mock_cfg = MagicMock()
        mock_cfg.global_config.mcp.host = "localhost"
        mock_cfg.global_config.mcp.port = 8080

        args = _make_triage_args(interaction_mode="interactive")

        with (
            patch(
                "application.cli.commands.triage.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.triage.compute_triage_readiness",
                return_value=MagicMock(enabled=True),
            ),
            patch("application.cli.commands.triage.ensure_triage_image"),
            patch("application.cli.commands.triage.ensure_triage_containers"),
            patch(
                "application.cli.commands.triage.create_triage_service",
                return_value=service,
            ),
            patch(
                "application.cli.commands.triage.load_active_repos",
                return_value=[],
            ),
            patch(
                "application.cli.commands.triage.mint_bearer_token",
                return_value="my-token",
            ),
            patch(
                "application.cli.commands.triage.ConfigManager",
                return_value=mock_cfg,
            ),
        ):
            code = _cmd_triage_with_mode(
                args, _stub_project_registry(), MagicMock(), Path("/app")
            )

        assert code == SUCCESS
        out = capsys.readouterr().out
        assert "mcp_bearer_token:" in out
        assert "my-token" in out


# -- Interactive scan rejects background-only flags ---------------------------


class TestInteractiveScanRejectsBackgroundFlags:
    """--only, --exclude, --api-key-override, --billing-method require background."""

    @pytest.mark.parametrize(
        "flag_name,flag_value",
        [
            ("only", "scan-xss-stored"),
            ("exclude", "scan-xss-stored"),
            ("api_key_override", "sk-test"),
            ("billing_method", "plan"),
        ],
        ids=["only", "exclude", "api-key-override", "billing-method"],
    )
    def test_interactive_rejects_flag(
        self,
        flag_name: str,
        flag_value: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        args = _make_args(**{flag_name: flag_value})

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan.load_active_repos",
                return_value=[MagicMock()],
            ),
        ):
            code = _cmd_scan_background(args, _stub_project_registry(), Path("/app"))

        assert code == INVALID_ARGS
        err = capsys.readouterr().err
        assert "requires --interaction-mode background" in err

    def test_background_mode_does_not_reject(self) -> None:
        """Flags are accepted when --interaction-mode=background is set."""
        args = _make_args(
            interaction_mode="background",
            only="scan-xss-stored",
        )

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan.load_active_repos",
                return_value=[MagicMock()],
            ),
            patch(
                "application.cli.commands.scan.resolve_display_slug",
            ),
            patch(
                "application.cli.commands.scan._schedule_scan_launch",
                return_value=SUCCESS,
            ),
        ):
            code = _cmd_scan_background(args, _stub_project_registry(), Path("/app"))

        assert code == SUCCESS


# -- Resume failure preserves run status --------------------------------------


class TestResumeFailurePreservesStatus:
    """ValueError during resume must NOT flip the run to failed."""

    def test_resume_keeps_status_on_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_run_repo = MagicMock()
        mock_launcher = MagicMock()
        mock_launcher.launch.side_effect = ValueError("bad billing config")

        with (
            patch("application.cli.commands.scan.ProjectPaths"),
            patch(
                "application.cli.commands.scan.create_scan_repos",
                return_value=(mock_run_repo, None, None, None),
            ),
            patch(
                "application.cli.commands.scan.create_finding_repo",
            ),
            patch(
                "application.cli.commands.scan.ConfigManager",
            ),
            patch(
                "application.scans.background_launcher.ScanBackgroundLauncher",
                return_value=mock_launcher,
            ),
            patch(
                "application.anthropic.mode_availability.BackgroundModeAvailabilityService",
            ),
        ):
            code = _schedule_scan_launch(
                project_id=1,
                project_name="proj",
                base_path="/app",
                interaction_mode="background",
                billing_method="plan",
                api_key_override=None,
                only=None,
                exclude=None,
                run_id=42,
                is_resume=True,
            )

        assert code == GENERAL_ERROR
        mock_run_repo.set_status.assert_not_called()
        err = capsys.readouterr().err
        assert "bad billing config" in err

    def test_new_run_marks_failed_on_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A fresh start (not resume) should still mark the run as failed."""
        mock_run_repo = MagicMock()
        mock_run_repo.create.return_value = 99
        mock_launcher = MagicMock()
        mock_launcher.launch.side_effect = ValueError("bad config")

        with (
            patch("application.cli.commands.scan.ProjectPaths"),
            patch(
                "application.cli.commands.scan.create_scan_repos",
                return_value=(mock_run_repo, None, None, None),
            ),
            patch(
                "application.cli.commands.scan.create_finding_repo",
            ),
            patch(
                "application.cli.commands.scan.ConfigManager",
            ),
            patch(
                "application.scans.background_launcher.ScanBackgroundLauncher",
                return_value=mock_launcher,
            ),
            patch(
                "application.anthropic.mode_availability.BackgroundModeAvailabilityService",
            ),
        ):
            code = _schedule_scan_launch(
                project_id=1,
                project_name="proj",
                base_path="/app",
                interaction_mode="background",
                billing_method="plan",
                api_key_override=None,
                only=None,
                exclude=None,
                run_id=None,
                is_resume=False,
            )

        assert code == GENERAL_ERROR
        mock_run_repo.set_status.assert_called_once_with(99, "failed")


# -- Resume defaults to run's original mode -----------------------------------


class TestResumeDefaultsToOriginalMode:
    """Resume uses the run's original interaction mode by default."""

    def test_scan_resume_background_run_defaults_background(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A background scan run (usage_pool=plan) resumes as background."""
        mock_run_repo = MagicMock()
        mock_run_repo.get_latest_usage_pool.return_value = "plan"

        args = _make_args(resume=42)

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan.create_scan_repos",
                return_value=(mock_run_repo, None, None, None),
            ),
            patch(
                "application.cli.commands.scan.ProjectPaths",
            ),
            patch(
                "application.cli.commands.scan._schedule_scan_launch",
                return_value=SUCCESS,
            ) as mock_launch,
        ):
            code = _cmd_scan_resume(args, _stub_project_registry(), Path("/app"))

        assert code == SUCCESS
        call_kwargs = mock_launch.call_args.kwargs
        assert call_kwargs["interaction_mode"] == "background"

    def test_scan_resume_run_without_usage_pool_defaults_interactive(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A scan run without usage_pool recorded resumes as interactive."""
        mock_run_repo = MagicMock()
        mock_run_repo.get_latest_usage_pool.return_value = None

        args = _make_args(resume=42)

        mock_cfg = MagicMock()
        mock_cfg.global_config.mcp.host = "localhost"
        mock_cfg.global_config.mcp.port = 8080

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan.create_scan_repos",
                return_value=(mock_run_repo, None, None, None),
            ),
            patch(
                "application.cli.commands.scan.ProjectPaths",
            ),
            patch(
                "application.cli.commands.scan.mint_bearer_token",
                return_value="test-token",
            ),
            patch(
                "application.cli.commands.scan.ConfigManager",
                return_value=mock_cfg,
            ),
        ):
            code = _cmd_scan_resume(args, _stub_project_registry(), Path("/app"))

        assert code == SUCCESS
        out = capsys.readouterr().out
        assert "mcp_url:" in out
        assert "mcp_bearer_token:" in out
        assert "test-token" in out

    def test_scan_resume_explicit_override_honored(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """User's explicit --interaction-mode overrides the inferred default."""
        args = _make_args(resume=42, interaction_mode="background")

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan._schedule_scan_launch",
                return_value=SUCCESS,
            ) as mock_launch,
        ):
            code = _cmd_scan_resume(args, _stub_project_registry(), Path("/app"))

        assert code == SUCCESS
        call_kwargs = mock_launch.call_args.kwargs
        assert call_kwargs["interaction_mode"] == "background"

    def test_scan_resume_interactive_prints_mcp_info_and_skips_launcher(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Interactive scan resume prints MCP connection info and skips launcher."""
        mock_run_repo = MagicMock()
        mock_run_repo.get_latest_usage_pool.return_value = None

        args = _make_args(resume=42, interaction_mode="interactive")

        mock_cfg = MagicMock()
        mock_cfg.global_config.mcp.host = "localhost"
        mock_cfg.global_config.mcp.port = 8080

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan.create_scan_repos",
                return_value=(mock_run_repo, None, None, None),
            ),
            patch(
                "application.cli.commands.scan.ProjectPaths",
            ),
            patch(
                "application.cli.commands.scan.mint_bearer_token",
                return_value="resume-token",
            ),
            patch(
                "application.cli.commands.scan.ConfigManager",
                return_value=mock_cfg,
            ),
            patch(
                "application.cli.commands.scan._schedule_scan_launch",
            ) as mock_launch,
        ):
            code = _cmd_scan_resume(args, _stub_project_registry(), Path("/app"))

        assert code == SUCCESS
        mock_launch.assert_not_called()
        out = capsys.readouterr().out
        assert "mcp_url:" in out
        assert "mcp_bearer_token:" in out
        assert "resume-token" in out

    def test_scan_resume_explicit_interactive_rejects_background_flags(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Interactive resume rejects --only and other background-only flags."""
        args = _make_args(
            resume=42, interaction_mode="interactive", only="scan-xss-stored"
        )

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
        ):
            code = _cmd_scan_resume(args, _stub_project_registry(), Path("/app"))

        assert code == INVALID_ARGS
        err = capsys.readouterr().err
        assert "--only" in err
        assert "requires --interaction-mode background" in err

    def test_triage_resume_background_run_defaults_background(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A background triage run (usage_pool=api) resumes as background."""
        mock_triage_repo = MagicMock()
        mock_triage_repo.get_latest_usage_pool.return_value = "api"

        service = MagicMock()
        handle = _make_handle(
            {
                "sessions_run": 1,
                "success": 1,
                "failed": 0,
                "incomplete": 0,
                "status": "completed",
            }
        )
        service.resume_triage.return_value = handle

        args = _make_triage_args(resume=42)

        with (
            patch(
                "application.cli.commands.triage.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.triage.make_store",
                return_value=(MagicMock(), MagicMock(), mock_triage_repo, MagicMock()),
            ),
            patch(
                "application.cli.commands.triage.compute_triage_readiness",
                return_value=MagicMock(enabled=True),
            ),
            patch(
                "application.cli.commands.triage.create_triage_service",
                return_value=service,
            ),
            patch(
                "application.cli.commands.triage.load_active_repos",
                return_value=[],
            ),
        ):
            code = _cmd_triage_resume(
                args, _stub_project_registry(), MagicMock(), Path("/app")
            )

        assert code == SUCCESS
        call_kwargs = service.resume_triage.call_args.kwargs
        assert call_kwargs["interaction_mode"] == "background"


# -- Error text uses --billing-method -----------------------------------------


class TestBillingMethodErrorText:
    """Error messages reference --billing-method, not --billing."""

    def test_scan_billing_error_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = _make_args(billing_method="plan")

        with (
            patch(
                "application.cli.commands.scan.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
            patch(
                "application.cli.commands.scan.load_active_repos",
                return_value=[MagicMock()],
            ),
        ):
            code = _cmd_scan_background(args, _stub_project_registry(), Path("/app"))

        assert code == INVALID_ARGS
        err = capsys.readouterr().err
        assert "--billing-method" in err
        assert '"--billing "' not in err

    def test_triage_billing_error_text(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        args = _make_triage_args(interaction_mode="interactive", billing_method="plan")

        with (
            patch(
                "application.cli.commands.triage.resolve_project",
                return_value=(1, MagicMock(name="testproj")),
            ),
        ):
            code = _cmd_triage_with_mode(
                args, _stub_project_registry(), MagicMock(), Path("/app")
            )

        assert code == INVALID_ARGS
        err = capsys.readouterr().err
        assert "--billing-method" in err
