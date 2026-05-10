"""Unit tests for core.detection.noir.noir_skip_reason."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from core.detection.noir import _is_node_app, noir_skip_reason


def _repo(
    *,
    path: str = "",
    dependencies_file: str = "",
) -> MagicMock:
    r = MagicMock()
    r.path = path
    r.dependencies_file = dependencies_file
    return r


def _write_deps(tmp_path: Path, content: str) -> str:
    p = tmp_path / "requirements.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


# Node.js detection via package.json


class TestNodeApp:
    def test_package_json_present_returns_reason(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        assert noir_skip_reason(_repo(path=str(tmp_path))) is not None

    def test_package_json_present_reason_mentions_nodejs(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        reason = noir_skip_reason(_repo(path=str(tmp_path)))
        assert reason is not None
        assert "Node" in reason

    def test_no_package_json_no_deps_returns_none(self, tmp_path: Path) -> None:
        assert noir_skip_reason(_repo(path=str(tmp_path))) is None

    def test_package_json_takes_precedence_over_deps(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text("{}", encoding="utf-8")
        deps = _write_deps(tmp_path, "aiohttp==3.9.0\n")
        reason = noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
        assert reason is not None
        assert "Node" in reason

    def test_empty_path_returns_none(self) -> None:
        assert _is_node_app("") is False

    def test_no_path_no_deps_returns_none(self) -> None:
        assert noir_skip_reason(_repo()) is None


# Unsupported framework detection via dependencies file


class TestUnsupportedFramework:
    def test_aiohttp_returns_reason(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "aiohttp==3.9.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )

    def test_aiohttp_reason_names_package(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "aiohttp==3.9.0\n")
        reason = noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
        assert reason is not None
        assert "aiohttp" in reason

    def test_bottle_detected(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "bottle>=0.12\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )

    def test_cherrypy_detected(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "CherryPy==18.9.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )

    def test_falcon_detected(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "falcon~=3.1\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )

    def test_pyramid_detected(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "pyramid\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )

    def test_comments_ignored(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "# aiohttp is not used here\nflask==3.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps)) is None
        )

    def test_blank_lines_ignored(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "\n\nflask==3.0\n\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps)) is None
        )


# Supported frameworks: must NOT skip


class TestSupportedFrameworks:
    def test_flask_returns_none(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "flask==3.0.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps)) is None
        )

    def test_django_returns_none(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "Django>=4.2\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps)) is None
        )

    def test_fastapi_returns_none(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "fastapi==0.110.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps)) is None
        )


# Edge cases


class TestEdgeCases:
    def test_empty_deps_file_returns_none(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps)) is None
        )

    def test_missing_deps_file_returns_none(self, tmp_path: Path) -> None:
        assert (
            noir_skip_reason(
                _repo(
                    path=str(tmp_path),
                    dependencies_file=str(tmp_path / "missing.txt"),
                )
            )
            is None
        )

    def test_no_deps_file_configured_returns_none(self, tmp_path: Path) -> None:
        assert noir_skip_reason(_repo(path=str(tmp_path), dependencies_file="")) is None

    def test_aiohttp_with_extras(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "aiohttp[speedups]==3.9.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )

    def test_package_name_is_case_insensitive(self, tmp_path: Path) -> None:
        deps = _write_deps(tmp_path, "AIOHTTP==3.9.0\n")
        assert (
            noir_skip_reason(_repo(path=str(tmp_path), dependencies_file=deps))
            is not None
        )
