"""Shared pytest configuration and skip markers for the tally test suite.

Skip markers (defined once here, used throughout the suite):
  requires_gitleaks: skip when the gitleaks binary is not installed
  requires_ollama: skip when Ollama is not reachable or not configured

These are module-level constants, not fixtures. Test files import them:
    from tests.conftest import requires_ollama
or rely on conftest auto-discovery if pytest adds tests/ to sys.path.
"""

from __future__ import annotations

import os
import shutil

import pytest

from core.config import ConfigManager
from infrastructure.llm.ollama_utils import verify_ollama_available


def pytest_configure(config: pytest.Config) -> None:
    if os.getenv("CI"):
        config.option.markexpr = "not integration and not e2e"


def _ollama_url() -> str | None:
    try:
        cfg = ConfigManager().load_global_config()
        return cfg.ollama.base_url if cfg.ollama else None
    except Exception:
        return None


_OLLAMA_URL = _ollama_url()
requires_gitleaks = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks binary not installed",
)
requires_xsstrike = pytest.mark.skipif(
    shutil.which("xsstrike") is None,
    reason="xsstrike binary not installed",
)
requires_ollama = pytest.mark.skipif(
    _OLLAMA_URL is None or not verify_ollama_available(_OLLAMA_URL),
    reason="Ollama not configured or not running",
)


def _docker_daemon_running() -> bool:
    import subprocess

    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


requires_docker = pytest.mark.skipif(
    not _docker_daemon_running(),
    reason="Docker not available or daemon not running",
)


@pytest.fixture(autouse=True)
def _restore_lock_registry():
    """Isolate lock_registry singleton state across all test scopes."""
    try:
        from application.locking.registry import get_registry

        reg = get_registry()
        saved = reg.snapshot()
        yield
        reg.restore(saved)
    except ImportError:
        yield
