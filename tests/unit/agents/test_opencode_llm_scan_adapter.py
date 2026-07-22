"""Tests for OpenCodeLlmScanAdapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from infrastructure.agents.opencode_llm_scan_adapter import (
    OpenCodeLlmScanAdapter,
)


class TestOpenCodeLlmScanAdapter:
    """Tests for OpenCode LLM scan adapter."""

    def test_parses_ndjson_text_events(self) -> None:
        """Adapter extracts text from NDJSON and parses findings."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps(
            [
                {
                    "file_path": "src/app.py",
                    "description": "Hardcoded API key",
                    "severity": "high",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "secrets",
                }
            ]
        )
        ndjson_output = "\n".join(
            [
                json.dumps({"type": "start"}),
                json.dumps(
                    {
                        "type": "text",
                        "part": {"text": findings_json},
                    }
                ),
                json.dumps({"type": "end"}),
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ndjson_output
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
        assert result.findings[0].description == "Hardcoded API key"
        assert result.findings[0].severity == "high"

    def test_handles_multiple_text_events(self) -> None:
        """Adapter concatenates text from multiple text events."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        # Split JSON across multiple text events
        findings_json = json.dumps(
            [
                {
                    "file_path": "test.js",
                    "description": "XSS vulnerability",
                    "severity": "medium",
                    "confidence": "probable",
                    "finding_type": ["vulnerability"],
                    "segment": "web",
                }
            ]
        )
        part1 = findings_json[:20]
        part2 = findings_json[20:]

        ndjson_output = "\n".join(
            [
                json.dumps({"type": "start"}),
                json.dumps({"type": "text", "part": {"text": part1}}),
                json.dumps({"type": "text", "part": {"text": part2}}),
                json.dumps({"type": "end"}),
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ndjson_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is True
        assert len(result.findings) == 1

    def test_ignores_non_text_events(self) -> None:
        """Adapter ignores events with type != 'text'."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps(
            [
                {
                    "file_path": "main.py",
                    "description": "SQL injection",
                    "severity": "critical",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "sast",
                }
            ]
        )
        ndjson_output = "\n".join(
            [
                json.dumps({"type": "start"}),
                json.dumps({"type": "progress", "data": "50%"}),
                json.dumps({"type": "text", "part": {"text": findings_json}}),
                json.dumps({"type": "end"}),
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ndjson_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is True
        assert len(result.findings) == 1

    def test_handles_malformed_ndjson_lines(self) -> None:
        """Adapter skips malformed JSON lines."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps(
            [
                {
                    "file_path": "app.py",
                    "description": "Auth bypass",
                    "severity": "critical",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "web",
                }
            ]
        )
        # Mix valid JSON with malformed lines
        ndjson_output = "\n".join(
            [
                "{not valid json",
                json.dumps({"type": "text", "part": {"text": findings_json}}),
                "another bad line}",
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ndjson_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is True
        assert len(result.findings) == 1

    def test_handles_nonzero_exit(self) -> None:
        """Adapter returns failure on non-zero exit code."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "opencode error: permission denied"

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "prompt",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is False
        assert result.findings == []
        assert "opencode exited" in (result.error or "")
        assert "permission denied" in (result.error or "")

    def test_handles_timeout(self) -> None:
        """Adapter returns failure on timeout."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        import subprocess as sp

        with patch(
            "subprocess.run",
            side_effect=sp.TimeoutExpired("cmd", 60),
        ):
            result = adapter.run_scan(
                "prompt",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is False
        assert result.findings == []
        assert "timeout" in (result.error or "").lower()

    def test_preserves_raw_output(self) -> None:
        """Adapter stores raw stdout for debugging."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        findings_json = json.dumps(
            [
                {
                    "file_path": "test.go",
                    "description": "Buffer overflow",
                    "severity": "critical",
                    "confidence": "confirmed",
                    "finding_type": ["vulnerability"],
                    "segment": "code",
                }
            ]
        )
        ndjson_output = json.dumps({"type": "text", "part": {"text": findings_json}})
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ndjson_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.raw_output == ndjson_output
        assert adapter.last_raw_output == ndjson_output

    def test_includes_model_flag(self) -> None:
        """Adapter includes model flag in docker-compose command."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
            model="llama2",
            provider_name="ollama",
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {"type": "text", "part": {"text": json.dumps([])}}
        )
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

            # Verify command includes model flag
            call_args = mock_run.call_args
            cmd = call_args[0][0]
            assert "--model" in cmd
            idx = cmd.index("--model")
            assert cmd[idx + 1] == "ollama/llama2"

    def test_handles_invalid_json_findings(self) -> None:
        """Adapter handles invalid finding JSON gracefully."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        # Invalid JSON in text event
        ndjson_output = json.dumps(
            {"type": "text", "part": {"text": "not valid json at all"}}
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ndjson_output
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is False
        assert result.findings == []
        assert result.error is not None

    def test_handles_empty_stdout(self) -> None:
        """Adapter handles empty stdout gracefully."""
        adapter = OpenCodeLlmScanAdapter(
            compose_path=Path("/tmp/compose.yaml"),
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = adapter.run_scan(
                "scan",
                timeout_seconds=60,
                cwd=Path("/workspace"),
            )

        assert result.success is False
        assert result.findings == []
        assert result.error is not None
