"""Unit tests for AuditRunner (application.audit.runner)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.audit.runner import AuditRunner


@pytest.fixture()
def audit_repo() -> MagicMock:
    repo = MagicMock()
    repo.log_event = MagicMock()
    return repo


@pytest.fixture()
def runner(audit_repo: MagicMock) -> AuditRunner:
    return AuditRunner(audit_repo)


class TestAuditRunner:
    async def test_success_path_returns_result(
        self, runner: AuditRunner, audit_repo: MagicMock
    ) -> None:
        fn = AsyncMock(return_value="ok")
        with patch(
            "application.audit.runner.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread:
            mock_to_thread.return_value = None
            result = await runner.run("tool", {}, fn)
        assert result == "ok"
        mock_to_thread.assert_called_once()
        assert mock_to_thread.call_args.args[0] is audit_repo.log_event
        assert mock_to_thread.call_args.args[3] is True

    async def test_generic_exception_reraises_and_logs(
        self, runner: AuditRunner, audit_repo: MagicMock
    ) -> None:
        fn = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(
            "application.audit.runner.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread:
            mock_to_thread.return_value = None
            with pytest.raises(RuntimeError):
                await runner.run("tool", {}, fn)
        mock_to_thread.assert_called_once()
        assert mock_to_thread.call_args.args[0] is audit_repo.log_event
        assert mock_to_thread.call_args.args[3] is False

    async def test_not_implemented_error_reraises_with_not_implemented_message(
        self, runner: AuditRunner, audit_repo: MagicMock
    ) -> None:
        fn = AsyncMock(side_effect=NotImplementedError)
        with patch(
            "application.audit.runner.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread:
            mock_to_thread.return_value = None
            with pytest.raises(NotImplementedError):
                await runner.run("tool", {}, fn)
        mock_to_thread.assert_called_once()
        assert mock_to_thread.call_args.args[0] is audit_repo.log_event
        assert mock_to_thread.call_args.args[4] == "not implemented"

    async def test_log_event_called_in_finally_on_success(
        self, runner: AuditRunner
    ) -> None:
        fn = AsyncMock(return_value=None)
        with patch(
            "application.audit.runner.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread:
            mock_to_thread.return_value = None
            await runner.run("tool", {}, fn)
        assert mock_to_thread.call_count == 1

    async def test_log_event_called_in_finally_on_exception(
        self, runner: AuditRunner
    ) -> None:
        fn = AsyncMock(side_effect=ValueError("err"))
        with patch(
            "application.audit.runner.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread:
            mock_to_thread.return_value = None
            with pytest.raises(ValueError):
                await runner.run("tool", {}, fn)
        assert mock_to_thread.call_count == 1
