"""Unit tests for get_tool_version (infrastructure.tools.version)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from infrastructure.tools.version import get_tool_version

_WHICH = "infrastructure.tools.version.shutil.which"
_RUN = "infrastructure.tools.version.subprocess.run"
_BINARY = "/usr/bin/mytool"


def test_returns_none_when_binary_not_on_path() -> None:
    with patch(_WHICH, return_value=None):
        assert get_tool_version("nonexistent") is None


def test_returns_first_line_of_stdout() -> None:
    proc = MagicMock(stdout="mytool 1.2.3\nextra line", stderr="")
    with (
        patch(_WHICH, return_value=_BINARY),
        patch(_RUN, return_value=proc),
    ):
        assert get_tool_version("mytool") == "mytool 1.2.3"


def test_falls_back_to_stderr_when_stdout_empty() -> None:
    proc = MagicMock(stdout="", stderr="version 2.0")
    with (
        patch(_WHICH, return_value=_BINARY),
        patch(_RUN, return_value=proc),
    ):
        assert get_tool_version("mytool") == "version 2.0"


def test_returns_none_when_output_empty() -> None:
    proc = MagicMock(stdout="", stderr="")
    with (
        patch(_WHICH, return_value=_BINARY),
        patch(_RUN, return_value=proc),
    ):
        assert get_tool_version("mytool") is None


def test_returns_none_on_file_not_found_error() -> None:
    with (
        patch(_WHICH, return_value=_BINARY),
        patch(_RUN, side_effect=FileNotFoundError),
    ):
        assert get_tool_version("mytool") is None


def test_returns_none_on_os_error() -> None:
    with (
        patch(_WHICH, return_value=_BINARY),
        patch(_RUN, side_effect=OSError),
    ):
        assert get_tool_version("mytool") is None
