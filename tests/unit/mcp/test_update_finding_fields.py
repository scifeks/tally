"""Unit tests for McpIngestService.update_finding_fields."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from application.mcp.finding_payload import FindingPayloadError
from application.mcp.ingest_service import McpIngestService


def _make_service(
    finding_repo: Any = None,
) -> McpIngestService:
    return McpIngestService(
        finding_repo=finding_repo or MagicMock(),
        run_repo=MagicMock(),
        repo_repo=MagicMock(),
    )


class TestUpdateFindingFields:
    @pytest.mark.parametrize(
        "status",
        ["active", "false_positive", "fixed", "wont_fix"],
    )
    def test_valid_status_delegates_to_repo(self, status: str) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.return_value = True
        svc = _make_service(finding_repo=repo)

        result = svc.update_finding_fields(1, status=status)

        assert result is True
        repo.update_analyst_fields.assert_called_once_with(
            1, {"status": status}, {}, source="cli"
        )

    def test_description_delegates_to_repo(self) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.return_value = True
        svc = _make_service(finding_repo=repo)

        result = svc.update_finding_fields(5, description="new desc")

        assert result is True
        repo.update_analyst_fields.assert_called_once_with(
            5, {"description": "new desc"}, {}, source="cli"
        )

    def test_both_fields_combined(self) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.return_value = True
        svc = _make_service(finding_repo=repo)

        result = svc.update_finding_fields(3, status="fixed", description="resolved")

        assert result is True
        call_columns = repo.update_analyst_fields.call_args[0][1]
        assert call_columns == {
            "status": "fixed",
            "description": "resolved",
        }

    def test_invalid_status_raises(self) -> None:
        svc = _make_service()

        with pytest.raises(FindingPayloadError, match="invalid"):
            svc.update_finding_fields(1, status="bogus")

    def test_finding_not_found_returns_false(self) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.return_value = False
        svc = _make_service(finding_repo=repo)

        result = svc.update_finding_fields(999, status="fixed")

        assert result is False
