"""Unit tests for triage dispatch-time credential checks in background mode."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.anthropic.mode_availability import BackgroundModeAvailability
from application.triage.triage_service import TriageService


class TestDispatchEnforcement:
    def test_background_plan_without_oauth_raises(self) -> None:
        """Background + plan billing requires an active OAuth session."""
        service = TriageService(
            run_repo=MagicMock(),
            triage_repo=MagicMock(),
            finding_repo=MagicMock(),
            audit_repo=MagicMock(),
            triage_run_registry=MagicMock(),
            lock_registry=MagicMock(),
        )
        cfg = MagicMock()
        cfg.claude.default_billing_method = None
        cfg.claude.api_key = ""
        availability = BackgroundModeAvailability(
            oauth_available=False,
            api_key_available=True,
            interactive_available=True,
            oauth_reason="No OAuth session found.",
        )

        with (
            patch("application.triage.triage_service.ConfigManager") as mock_cm,
            patch(
                "application.triage.triage_service.BackgroundModeAvailabilityService"
            ) as mock_avail_cls,
        ):
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            with pytest.raises(ValueError, match="plan"):
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    billing_method="plan",
                )

    def test_background_api_without_key_raises(self) -> None:
        """Background + api billing requires an API key."""
        service = TriageService(
            run_repo=MagicMock(),
            triage_repo=MagicMock(),
            finding_repo=MagicMock(),
            audit_repo=MagicMock(),
            triage_run_registry=MagicMock(),
            lock_registry=MagicMock(),
        )
        cfg = MagicMock()
        cfg.claude.default_billing_method = None
        cfg.claude.api_key = ""
        availability = BackgroundModeAvailability(
            oauth_available=True,
            api_key_available=False,
            interactive_available=True,
            api_key_reason="No API key configured.",
        )

        with (
            patch("application.triage.triage_service.ConfigManager") as mock_cm,
            patch(
                "application.triage.triage_service.BackgroundModeAvailabilityService"
            ) as mock_avail_cls,
        ):
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            with pytest.raises(ValueError, match="api"):
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    billing_method="api",
                )
