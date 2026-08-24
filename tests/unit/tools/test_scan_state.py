"""Unit tests for infrastructure.tools.wrappers.utils.scan_state."""

from __future__ import annotations

from unittest.mock import patch

from infrastructure.tools.wrappers.utils import install_fallback, pip_deps
from infrastructure.tools.wrappers.utils.scan_state import (
    reset_scan_scoped_state,
)


class TestResetScanScopedState:
    def setup_method(self) -> None:
        install_fallback.reset_attempted()
        pip_deps.reset_attempted()

    def test_reset_clears_both_dedup_sets(self, tmp_path) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.install_fallback.subprocess.run",
            return_value=type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})(),
        ):
            install_fallback.ensure_lockfile(
                "npm-audit",
                str(tmp_path),
                "package-lock.json",
                ["npm", "install"],
            )

        with patch(
            "infrastructure.tools.wrappers.utils.pip_deps.subprocess.run",
            return_value=type("R", (), {"returncode": 1})(),
        ):
            pip_deps.find_or_generate_requirements(str(tmp_path))

        assert ("npm-audit", str(tmp_path)) in install_fallback._attempted
        assert str(tmp_path) in pip_deps._attempted

        reset_scan_scoped_state()

        assert len(install_fallback._attempted) == 0
        assert len(pip_deps._attempted) == 0
