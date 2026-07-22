"""Unit tests for Claude LLM scan adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.agents.claude_llm_scan_adapter import ClaudeLlmScanAdapter


class TestClaudeLlmScanAdapter:
    def test_extract_result_from_json_wrapper(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps(
            [
                {
                    "file_path": "a.py",
                    "description": "XSS vulnerability",
                    "severity": "high",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "sast",
                }
            ]
        )
        wrapper = json.dumps(
            {
                "result": findings_json,
                "is_error": False,
            }
        )
        text = adapter._extract_result(wrapper)
        assert "a.py" in text
        assert "XSS" in text

    def test_extract_result_handles_error(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        wrapper = json.dumps(
            {
                "result": "something went wrong",
                "is_error": True,
            }
        )
        with pytest.raises(ValueError, match="claude reported an error"):
            adapter._extract_result(wrapper)

    def test_extract_result_empty_stdout(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        with pytest.raises(ValueError, match="empty stdout"):
            adapter._extract_result("")

    def test_extract_result_invalid_json(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        with pytest.raises(ValueError, match="not valid JSON"):
            adapter._extract_result("not json at all {")

    def test_extract_result_not_object(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        with pytest.raises(ValueError, match="not an object"):
            adapter._extract_result(json.dumps(["array", "not", "object"]))

    def test_extract_result_missing_result_field(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        wrapper = json.dumps(
            {
                "is_error": False,
            }
        )
        with pytest.raises(ValueError, match="missing 'result' string field"):
            adapter._extract_result(wrapper)

    def test_run_scan_returns_findings(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps(
            [
                {
                    "file_path": "src/app.py",
                    "description": "SQL injection vulnerability",
                    "severity": "high",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "sast",
                }
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "result": findings_json,
                "is_error": False,
            }
        )
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan prompt",
                timeout_seconds=300,
                cwd=Path("/workspace"),
            )
        assert result.success is True
        assert len(result.findings) == 1
        assert result.findings[0].file_path == "src/app.py"
        assert result.findings[0].severity == "high"

    def test_run_scan_handles_nonzero_exit(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "container error"

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan prompt",
                timeout_seconds=300,
                cwd=Path("/workspace"),
            )
        assert result.success is False
        assert "container error" in (result.error or "")

    def test_run_scan_handles_timeout(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )

        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("cmd", 1),
        ):
            result = adapter.run_scan(
                "scan prompt",
                timeout_seconds=1,
                cwd=Path("/workspace"),
            )
        assert result.success is False
        assert result.error == "timeout"

    def test_run_scan_handles_invalid_json_output(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan prompt",
                timeout_seconds=300,
                cwd=Path("/workspace"),
            )
        assert result.success is False
        assert "not valid JSON" in (result.error or "")

    def test_run_scan_with_parse_errors(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        # Valid JSON but with validation errors (missing severity)
        findings_json = json.dumps(
            [
                {
                    "file_path": "src/app.py",
                    "description": "Missing severity",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "sast",
                }
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "result": findings_json,
                "is_error": False,
            }
        )
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan prompt",
                timeout_seconds=300,
                cwd=Path("/workspace"),
            )
        # success=True because docker succeeded, but findings are empty
        # due to validation errors, and error contains the messages
        assert result.success is True
        assert len(result.findings) == 0
        assert result.error is not None
        assert "severity" in result.error.lower()

    def test_last_raw_output_populated(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps([])
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "result": findings_json,
                "is_error": False,
            }
        )
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            adapter.run_scan(
                "scan prompt",
                timeout_seconds=300,
                cwd=Path("/workspace"),
            )
        assert adapter.last_raw_output == mock_result.stdout

    def test_prepare_session_yields_prepared_session(self) -> None:
        adapter = ClaudeLlmScanAdapter(
            model="test-model",
            compose_path=Path("/tmp/compose.yaml"),
        )
        app_root = Path("/workspace")
        with adapter.prepare_session(
            project="test-project",
            run_id=1,
            app_root=app_root,
        ) as session:
            assert session.cwd == app_root
