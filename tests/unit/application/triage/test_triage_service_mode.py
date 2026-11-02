"""Tests for interaction_mode and billing_method validation in TriageService."""

from __future__ import annotations

from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from application.anthropic.mode_availability import BackgroundModeAvailability
from application.triage.factory import ResolvedTriageConfig
from application.triage.triage_service import (
    ResolvedBilling,
    TriageConfigurationError,
    TriageService,
)


def _make_service() -> TriageService:
    return TriageService(
        run_repo=MagicMock(),
        triage_repo=MagicMock(),
        finding_repo=MagicMock(),
        audit_repo=MagicMock(),
        lock_registry=MagicMock(),
        triage_run_registry=MagicMock(),
    )


def _make_config(
    *,
    default_billing: str | None = None,
    api_key: str = "sk-test-key",
) -> MagicMock:
    cfg = MagicMock()
    cfg.claude.default_billing_method = default_billing
    cfg.claude.api_key = api_key
    return cfg


def _make_availability(
    *,
    oauth_available: bool = True,
    api_key_available: bool = True,
) -> BackgroundModeAvailability:
    return BackgroundModeAvailability(
        oauth_available=oauth_available,
        api_key_available=api_key_available,
        interactive_available=True,
        oauth_reason=None if oauth_available else "No OAuth session found.",
        api_key_reason=None if api_key_available else "No API key configured.",
    )


def _background_patches():
    """Patches that keep background-mode tests isolated from disk."""
    return (
        patch("application.triage.triage_service.ConfigManager"),
        patch("application.triage.triage_service.BackgroundModeAvailabilityService"),
        patch("application.triage.triage_service.resolve_triage_config"),
    )


def _stub_resolve_config() -> ResolvedTriageConfig:
    """Minimal config returned by the patched resolve_triage_config."""
    return ResolvedTriageConfig(
        provider_name="claude",
        base_url="http://localhost",
        model="test-model",
        timeout_seconds=300,
        retry_count=0,
        debug=False,
    )


class TestInteractiveModeValidation:
    def test_rejects_billing_method(self) -> None:
        service = _make_service()
        with pytest.raises(ValueError, match="billing_method"):
            service.start_triage(
                base_path="/tmp/test",
                project_id=1,
                project_name="test",
                tool_registry=MagicMock(),
                interaction_mode="interactive",
                billing_method="plan",
            )


class TestNullModeBillingGuard:
    def test_none_mode_with_billing_raises(self) -> None:
        service = _make_service()
        with pytest.raises(
            TriageConfigurationError,
            match="billing_method requires interaction_mode='background'",
        ):
            service.start_triage(
                base_path="/tmp/test",
                project_id=1,
                project_name="test",
                tool_registry=MagicMock(),
                interaction_mode=None,
                billing_method="api",
            )

    def test_none_mode_without_billing_allowed(self) -> None:
        """Legacy callers passing no mode or billing should work normally."""
        service = _make_service()
        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured"
        ):
            handle = service.start_triage(
                base_path="/tmp/test",
                project_id=1,
                project_name="test",
                tool_registry=MagicMock(),
                scan_run_id=42,
            )
            assert handle.scan_run_id == 42


class TestBackgroundModeValidation:
    def test_plan_without_oauth_raises(self) -> None:
        service = _make_service()
        cfg = _make_config()
        availability = _make_availability(oauth_available=False)
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            with pytest.raises(ValueError, match="plan"):
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    billing_method="plan",
                )

    def test_api_without_key_raises(self) -> None:
        service = _make_service()
        cfg = _make_config()
        availability = _make_availability(api_key_available=False)
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            with pytest.raises(ValueError, match="api"):
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    billing_method="api",
                )

    def test_defaults_to_plan_when_no_billing_specified(self) -> None:
        service = _make_service()
        cfg = _make_config(default_billing=None)
        availability = _make_availability()
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            handle = service.start_triage(
                base_path="/tmp/test",
                project_id=1,
                project_name="test",
                tool_registry=MagicMock(),
                interaction_mode="background",
                scan_run_id=42,
            )
            assert handle.scan_run_id == 42

    def test_uses_config_default_billing_method(self) -> None:
        service = _make_service()
        cfg = _make_config(default_billing="api")
        availability = _make_availability(oauth_available=False)
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            handle = service.start_triage(
                base_path="/tmp/test",
                project_id=1,
                project_name="test",
                tool_registry=MagicMock(),
                interaction_mode="background",
                scan_run_id=42,
            )
            assert handle.scan_run_id == 42

    def test_explicit_billing_overrides_config_default(self) -> None:
        service = _make_service()
        cfg = _make_config(default_billing="api")
        availability = _make_availability(oauth_available=False)
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            with pytest.raises(ValueError, match="plan"):
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    billing_method="plan",
                )


class TestBackgroundModePlumbing:
    """Verify resolved config flows from start_triage through _dispatch."""

    def test_background_dispatches_with_claude_sdk_config(self) -> None:
        """background mode builds a ResolvedTriageConfig with provider=claude_sdk
        and passes it through _dispatch to the worker thread."""
        service = _make_service()
        cfg = _make_config(default_billing=None, api_key="sk-from-config")
        availability = _make_availability()
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    scan_run_id=42,
                )

                call_kwargs = mock_dispatch.call_args.kwargs
                rc = call_kwargs["resolved_config"]
                assert isinstance(rc, ResolvedTriageConfig)
                assert rc.provider_name == "claude_sdk"
                assert rc.billing_method == "plan"
                assert rc.auto_failover is True
                assert rc.api_key_source == "sk-from-config"

    def test_background_api_billing_with_explicit_key(self) -> None:
        service = _make_service()
        cfg = _make_config(default_billing=None, api_key="sk-config")
        availability = _make_availability()
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    billing_method="api",
                    api_key="sk-explicit",
                    scan_run_id=42,
                )

                rc = mock_dispatch.call_args.kwargs["resolved_config"]
                assert rc.provider_name == "claude_sdk"
                assert rc.billing_method == "api"
                assert rc.api_key_source == "sk-explicit"
                assert rc.auto_failover is False

    def test_background_config_default_api_no_failover(self) -> None:
        service = _make_service()
        cfg = _make_config(default_billing="api", api_key="sk-config")
        availability = _make_availability()
        p_cm, p_avail, p_resolve = _background_patches()

        with p_cm as mock_cm, p_avail as mock_avail_cls, p_resolve as mock_resolve:
            mock_cm.return_value.global_config = cfg
            mock_avail_cls.return_value.evaluate.return_value = availability
            mock_resolve.return_value = _stub_resolve_config()

            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    interaction_mode="background",
                    scan_run_id=42,
                )

                rc = mock_dispatch.call_args.kwargs["resolved_config"]
                assert rc.billing_method == "api"
                assert rc.auto_failover is False

    def test_none_mode_dispatches_without_resolved_config(self) -> None:
        service = _make_service()
        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured"
        ):
            with patch.object(service, "_dispatch") as mock_dispatch:
                mock_dispatch.return_value = MagicMock(scan_run_id=42)
                service.start_triage(
                    base_path="/tmp/test",
                    project_id=1,
                    project_name="test",
                    tool_registry=MagicMock(),
                    scan_run_id=42,
                )
                assert mock_dispatch.call_args.kwargs["resolved_config"] is None


class TestResolveBillingMethod:
    @pytest.mark.parametrize(
        ("explicit", "config_default", "expected_method", "expected_failover"),
        [
            ("plan", "api", "plan", False),
            ("api", "plan", "api", False),
            (None, "plan", "plan", False),
            (None, "api", "api", False),
            (None, None, "plan", True),
        ],
        ids=[
            "explicit-plan-wins",
            "explicit-api-wins",
            "config-default-plan",
            "config-default-api",
            "fallback-to-plan-with-failover",
        ],
    )
    def test_resolution_priority(
        self,
        explicit: Literal["plan", "api"] | None,
        config_default: str | None,
        expected_method: str,
        expected_failover: bool,
    ) -> None:
        cfg = _make_config(default_billing=config_default)
        result = TriageService._resolve_billing_method(cfg, explicit)
        assert isinstance(result, ResolvedBilling)
        assert result.method == expected_method
        assert result.auto_failover_permitted == expected_failover


class TestValidateBackgroundCredentials:
    def test_plan_requires_oauth(self) -> None:
        avail = _make_availability(oauth_available=False)
        with pytest.raises(ValueError, match="plan"):
            TriageService._validate_background_credentials("plan", avail)

    def test_api_requires_api_key(self) -> None:
        avail = _make_availability(api_key_available=False)
        with pytest.raises(ValueError, match="api"):
            TriageService._validate_background_credentials("api", avail)

    def test_plan_passes_with_oauth(self) -> None:
        avail = _make_availability(oauth_available=True)
        TriageService._validate_background_credentials("plan", avail)

    def test_api_passes_with_key(self) -> None:
        avail = _make_availability(api_key_available=True)
        TriageService._validate_background_credentials("api", avail)
