"""Unit tests for Docker container SCA tool probing."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from infrastructure.tools.wrappers.utils.container_tool_probe import (
    SCA_TOOLS_BY_LANGUAGE,
    probe_container_tools,
)


class TestScaToolsByLanguage:
    def test_python_maps_to_pip_audit(self) -> None:
        assert ("pip-audit", "pip-audit") in SCA_TOOLS_BY_LANGUAGE["python"]

    def test_php_maps_to_composer(self) -> None:
        assert ("composer-audit", "composer") in SCA_TOOLS_BY_LANGUAGE["php"]

    def test_node_variants_map_to_npm(self) -> None:
        npm_entry = ("npm-audit", "npm")
        for lang in ("javascript", "typescript", "node"):
            assert npm_entry in SCA_TOOLS_BY_LANGUAGE[lang]


class TestProbeContainerTools:
    @pytest.fixture()
    def _mock_run(self):
        with patch(
            "infrastructure.tools.wrappers.utils.container_tool_probe.subprocess.run"
        ) as mock:
            yield mock

    def test_returns_detected_tool_paths(self, _mock_run) -> None:
        _mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="/usr/local/bin/pip-audit\n"
        )
        result = probe_container_tools("app", ["python"])
        assert result == {"pip-audit": "/usr/local/bin/pip-audit"}

    def test_skips_tools_when_which_fails(self, _mock_run) -> None:
        _mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=""
        )
        result = probe_container_tools("app", ["python"])
        assert result == {}

    def test_ignores_unmapped_languages(self, _mock_run) -> None:
        result = probe_container_tools("app", ["go", "ruby"])
        _mock_run.assert_not_called()
        assert result == {}

    def test_deduplicates_across_language_aliases(self, _mock_run) -> None:
        _mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="/usr/bin/npm\n"
        )
        result = probe_container_tools("app", ["javascript", "typescript", "node"])
        assert result == {"npm-audit": "/usr/bin/npm"}
        assert _mock_run.call_count == 1

    def test_returns_empty_on_timeout(self, _mock_run) -> None:
        _mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=10)
        result = probe_container_tools("app", ["python"])
        assert result == {}

    def test_returns_empty_on_exception(self, _mock_run) -> None:
        _mock_run.side_effect = FileNotFoundError("docker not found")
        result = probe_container_tools("app", ["python"])
        assert result == {}

    def test_partial_detection(self, _mock_run) -> None:
        def side_effect(*args, **_kw):
            cmd = args[0]
            binary = cmd[-1]
            if binary == "pip-audit":
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout="/usr/local/bin/pip-audit\n",
                )
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="")

        _mock_run.side_effect = side_effect
        result = probe_container_tools("app", ["python", "php"])
        assert result == {"pip-audit": "/usr/local/bin/pip-audit"}
        assert "composer-audit" not in result
