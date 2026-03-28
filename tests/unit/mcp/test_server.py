"""Unit tests for tally_mcp.server tool handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import tally_mcp.server as server_module
from tally_mcp.server import get_findings_batch, update_findings_batch
from tally_mcp.tools import findings


class TestAuditRunnerIsNoneBeforeMain:
    def test_audit_runner_is_none_before_main(self):
        """_audit_runner must be None when the module is imported without main()."""
        assert server_module._audit_runner is None


class TestGetFindingsBatch:
    @pytest.mark.asyncio
    async def test_delegates_to_audit_runner(self):
        mock_runner = MagicMock()
        expected = [{"id": 1, "tool": "semgrep"}, {"id": 2, "tool": "nmap"}]
        mock_runner.run = AsyncMock(return_value=expected)

        with patch.object(server_module, "_audit_runner", mock_runner):
            result = await get_findings_batch([1, 2])

        assert result == expected
        mock_runner.run.assert_called_once_with(
            "get_findings_batch",
            {"finding_ids": [1, 2]},
            findings.get_findings_batch,
            [1, 2],
        )

    @pytest.mark.asyncio
    async def test_raises_if_runner_not_set(self):
        with patch.object(server_module, "_audit_runner", None):
            with pytest.raises(AssertionError):
                await get_findings_batch([1])


class TestUpdateFindingsBatch:
    @pytest.mark.asyncio
    async def test_delegates_to_audit_runner(self):
        mock_runner = MagicMock()
        payload = [{"finding_id": 1, "severity": "high"}]
        expected = {"1": {"finding_id": 1, "status": "updated"}}
        mock_runner.run = AsyncMock(return_value=expected)

        with patch.object(server_module, "_audit_runner", mock_runner):
            result = await update_findings_batch(payload)

        assert result == expected
        mock_runner.run.assert_called_once_with(
            "update_findings_batch",
            {"updates": payload},
            findings.update_findings_batch,
            payload,
        )

    @pytest.mark.asyncio
    async def test_raises_if_runner_not_set(self):
        with patch.object(server_module, "_audit_runner", None):
            with pytest.raises(AssertionError):
                await update_findings_batch([{"finding_id": 1}])
