"""Unit tests for triage dispatch-time mode enforcement."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from application.triage.triage_service import TriageService
from domain.triage.errors import TriageModeError


class TestDispatchEnforcement:
    def test_claude_without_key_raises_mode_error(self) -> None:
        """Direct auto-triage call with claude and no key."""
        service = TriageService(
            run_repo=MagicMock(),
            triage_repo=MagicMock(),
            finding_repo=MagicMock(),
            audit_repo=MagicMock(),
            triage_run_registry=MagicMock(),
            lock_registry=MagicMock(),
        )
        mock_cfg = MagicMock()
        mock_cfg.triage_inference.provider = "claude"
        mock_cfg.claude.api_key = ""

        with (
            patch(
                "application.triage.triage_service.ensure_triage_backend_configured",
                return_value="claude",
            ),
            patch("application.triage.triage_service.ConfigManager") as mock_cm,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_cm.return_value.global_config = mock_cfg
            with pytest.raises(TriageModeError):
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                )
