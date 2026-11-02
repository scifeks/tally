"""Tests for TriageService.resume_triage validation and config plumbing."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.triage.factory import ResolvedTriageConfig
from application.triage.triage_service import (
    TriageConfigurationError,
    TriageNotResumableError,
    TriageService,
)
from domain.triage.entry import TriageRunSummary


def _make_service(*, triage_repo: MagicMock | None = None) -> TriageService:
    return TriageService(
        run_repo=MagicMock(),
        triage_repo=triage_repo or MagicMock(),
        finding_repo=MagicMock(),
        audit_repo=MagicMock(),
        lock_registry=MagicMock(),
        triage_run_registry=MagicMock(),
    )


def _make_summary(status: str) -> TriageRunSummary:
    return TriageRunSummary(
        scan_run_id=42,
        status=status,
        started_at="2024-01-01T00:00:00",
        finished_at=None,
        total_findings=5,
        processed_findings=0,
        total_batches=1,
        counts_by_status={},
    )


def _stub_resolve_config() -> ResolvedTriageConfig:
    return ResolvedTriageConfig(
        provider_name="claude",
        base_url="http://localhost",
        model="test-model",
        timeout_seconds=300,
        retry_count=0,
        debug=False,
    )


def _make_config(
    *,
    api_key: str = "sk-test-key",
) -> MagicMock:
    cfg = MagicMock()
    cfg.claude.default_billing_method = None
    cfg.claude.api_key = api_key
    return cfg


def _background_patches():
    return (
        patch("application.triage.triage_service.ConfigManager"),
        patch("application.triage.triage_service.BackgroundModeAvailabilityService"),
        patch("application.triage.triage_service.resolve_triage_config"),
    )


def _make_availability(
    *, oauth_available: bool = True, api_key_available: bool = True
) -> MagicMock:
    avail = MagicMock()
    avail.oauth_available = oauth_available
    avail.api_key_available = api_key_available
    avail.oauth_reason = None if oauth_available else "No OAuth session found."
    avail.api_key_reason = None if api_key_available else "No API key configured."
    return avail


_RESUME_KWARGS: dict[str, Any] = dict(
    base_path="/tmp/test",
    project_id=1,
    project_name="test",
    scan_run_id=42,
    tool_registry=MagicMock(),
)


class TestResumeTriageValidation:
    def test_none_mode_with_billing_raises_configuration_error(self) -> None:
        service = _make_service()
        with pytest.raises(
            TriageConfigurationError,
            match="billing_method requires interaction_mode='background'",
        ):
            service.resume_triage(
                **_RESUME_KWARGS,
                interaction_mode=None,
                billing_method="api",
            )

    def test_done_run_raises_not_resumable(self) -> None:
        triage_repo = MagicMock()
        triage_repo.summarize_for_run.return_value = _make_summary("done")
        service = _make_service(triage_repo=triage_repo)

        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured"
        ):
            with pytest.raises(TriageNotResumableError) as exc_info:
                service.resume_triage(**_RESUME_KWARGS)
        assert exc_info.value.status == "done"

    def test_rate_limited_run_is_resumable(self) -> None:
        triage_repo = MagicMock()
        triage_repo.summarize_for_run.return_value = _make_summary("rate_limited")
        service = _make_service(triage_repo=triage_repo)

        p_cm, p_avail, p_resolve = _background_patches()
        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = _make_config()
            mock_avail_cls.return_value.evaluate.return_value = _make_availability()
            mock_resolve.return_value = _stub_resolve_config()

            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.resume_triage(
                    **_RESUME_KWARGS,
                    interaction_mode="background",
                    billing_method="api",
                    api_key="sk-x",
                )


class TestResumeTriageConfigPlumbing:
    def test_background_api_builds_resolved_config(self) -> None:
        triage_repo = MagicMock()
        triage_repo.summarize_for_run.return_value = _make_summary("failed")
        service = _make_service(triage_repo=triage_repo)

        p_cm, p_avail, p_resolve = _background_patches()
        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = _make_config()
            mock_avail_cls.return_value.evaluate.return_value = _make_availability()
            mock_resolve.return_value = _stub_resolve_config()

            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.resume_triage(
                    **_RESUME_KWARGS,
                    interaction_mode="background",
                    billing_method="api",
                    api_key="sk-x",
                )

                rc = mock_dispatch.call_args.kwargs["resolved_config"]
                assert isinstance(rc, ResolvedTriageConfig)
                assert rc.provider_name == "claude_sdk"
                assert rc.billing_method == "api"
                assert rc.api_key_source == "sk-x"
                assert rc.auto_failover is False

    def test_background_uses_config_api_key_when_no_arg(self) -> None:
        triage_repo = MagicMock()
        triage_repo.summarize_for_run.return_value = _make_summary("running")
        service = _make_service(triage_repo=triage_repo)

        p_cm, p_avail, p_resolve = _background_patches()
        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = _make_config(api_key="sk-cfg")
            mock_avail_cls.return_value.evaluate.return_value = _make_availability()
            mock_resolve.return_value = _stub_resolve_config()

            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.resume_triage(
                    **_RESUME_KWARGS,
                    interaction_mode="background",
                    billing_method="api",
                )

                rc = mock_dispatch.call_args.kwargs["resolved_config"]
                assert rc.api_key_source == "sk-cfg"

    def test_resume_forwards_is_resume_flag(self) -> None:
        triage_repo = MagicMock()
        triage_repo.summarize_for_run.return_value = _make_summary("failed")
        service = _make_service(triage_repo=triage_repo)

        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured"
        ):
            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.resume_triage(**_RESUME_KWARGS)
                assert mock_dispatch.call_args.kwargs["is_resume"] is True
