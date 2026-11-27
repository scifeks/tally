"""Tests for the storage result IngestHandler reports."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.pipeline.handlers import IngestHandler
from domain.pipeline.events import EventBus, IngestCompleted, ToolCompleted
from domain.tools.base import ToolResult

_FINDING = {"tool": "zap", "url": "http://x/a", "description": "d"}


def _result(success: bool, parsed_data: dict) -> ToolResult:
    return ToolResult(
        tool_name="zap",
        success=success,
        output="",
        parsed_data=parsed_data,
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


def _tool_handler(normalize_error: Exception | None = None) -> MagicMock:
    tool_handler = MagicMock()
    tool_handler.domain = "web"
    tool_handler.segment = "web"
    tool_handler.fingerprint_key.return_value = "key"
    if normalize_error is not None:
        tool_handler.normalize.side_effect = normalize_error
    else:
        tool_handler.normalize.return_value = [dict(_FINDING)]
    return tool_handler


def _handle(
    result: ToolResult, tool_handler: MagicMock | None
) -> tuple[IngestCompleted, MagicMock]:
    bus = EventBus()
    received: list[IngestCompleted] = []
    bus.subscribe(IngestCompleted, received.append)
    finding_repo = MagicMock()
    finding_repo.get_ids_by_fingerprints.return_value = [7]
    repo_repo = MagicMock()
    repo_repo.find_id_by_name.return_value = 3
    handler = IngestHandler(bus, finding_repo=finding_repo, repo_repo=repo_repo)
    with patch(
        "application.rag.ingestor.ToolHandlerFactory.load",
        return_value=tool_handler,
    ):
        handler.handle(
            ToolCompleted(result, "shop", 1, "proj", "/tmp", repo="shop", service="api")
        )
    return received[0], finding_repo


class TestIngestHandlerStorageResult:
    @pytest.mark.parametrize(
        ("result", "tool_handler", "stored"),
        [
            pytest.param(
                _result(True, {"findings": [1]}), _tool_handler(), True, id="stored"
            ),
            pytest.param(_result(True, {}), _tool_handler(), True, id="nothing-found"),
            pytest.param(
                _result(True, {"findings": [1]}), None, True, id="no-ingest-handler"
            ),
            pytest.param(
                _result(False, {"findings": [1]}), _tool_handler(), False, id="failed"
            ),
            pytest.param(
                _result(True, {"error": "boom"}), _tool_handler(), False, id="error-key"
            ),
            pytest.param(
                _result(True, {"findings": [1]}),
                _tool_handler(RuntimeError("boom")),
                False,
                id="storing-raised",
            ),
        ],
    )
    def test_stored_flag_and_identity(
        self, result: ToolResult, tool_handler: MagicMock | None, stored: bool
    ) -> None:
        completed, _ = _handle(result, tool_handler)
        assert completed.stored is stored
        assert (completed.tool, completed.repo, completed.service) == (
            "zap",
            "shop",
            "api",
        )

    def test_service_reaches_the_columns_but_not_the_fingerprint(self) -> None:
        tool_handler = _tool_handler()
        _, finding_repo = _handle(_result(True, {"findings": [1]}), tool_handler)
        normalized = finding_repo.insert_findings.call_args.args[1]
        assert normalized[0].columns["service"] == "api"
        fingerprinted = tool_handler.fingerprint_key.call_args.args[0]
        assert "service" not in fingerprinted
