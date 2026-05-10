"""Tests for dependency directory detection."""

from __future__ import annotations

from pathlib import Path

from infrastructure.tools.dependency_detection import (
    build_exclude_path_prefixes,
    detect_dependency_dirs,
)


def _touch(path: Path) -> None:
    path.write_text("")


class TestDetectDependencyDirs:
    def test_composer_json_with_vendor_dir(self, tmp_path: Path) -> None:
        _touch(tmp_path / "composer.json")
        (tmp_path / "vendor").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "vendor" in result

    def test_composer_lock_with_vendor_dir(self, tmp_path: Path) -> None:
        _touch(tmp_path / "composer.lock")
        (tmp_path / "vendor").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "vendor" in result

    def test_package_json_with_node_modules(self, tmp_path: Path) -> None:
        _touch(tmp_path / "package.json")
        (tmp_path / "node_modules").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "node_modules" in result

    def test_package_lock_json_with_node_modules(self, tmp_path: Path) -> None:
        _touch(tmp_path / "package-lock.json")
        (tmp_path / "node_modules").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "node_modules" in result

    def test_yarn_lock_with_node_modules(self, tmp_path: Path) -> None:
        _touch(tmp_path / "yarn.lock")
        (tmp_path / "node_modules").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "node_modules" in result

    def test_pnpm_lock_with_node_modules(self, tmp_path: Path) -> None:
        _touch(tmp_path / "pnpm-lock.yaml")
        (tmp_path / "node_modules").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "node_modules" in result

    def test_requirements_txt_with_venv(self, tmp_path: Path) -> None:
        _touch(tmp_path / "requirements.txt")
        (tmp_path / "venv").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "venv" in result

    def test_requirements_txt_with_dot_venv(self, tmp_path: Path) -> None:
        _touch(tmp_path / "requirements.txt")
        (tmp_path / ".venv").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert ".venv" in result

    def test_pipfile_with_venv(self, tmp_path: Path) -> None:
        _touch(tmp_path / "Pipfile")
        (tmp_path / ".venv").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert ".venv" in result

    def test_pyproject_toml_with_venv(self, tmp_path: Path) -> None:
        _touch(tmp_path / "pyproject.toml")
        (tmp_path / "venv").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "venv" in result

    def test_gemfile_with_vendor_bundle(self, tmp_path: Path) -> None:
        _touch(tmp_path / "Gemfile")
        vendor = tmp_path / "vendor" / "bundle"
        vendor.mkdir(parents=True)
        result = detect_dependency_dirs(tmp_path)
        assert "vendor/bundle" in result

    def test_go_mod_with_vendor_dir(self, tmp_path: Path) -> None:
        _touch(tmp_path / "go.mod")
        (tmp_path / "vendor").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "vendor" in result

    def test_lockfile_present_but_dep_dir_absent(self, tmp_path: Path) -> None:
        """Lockfile without corresponding dependency dir → not excluded."""
        _touch(tmp_path / "composer.json")
        # vendor/ does NOT exist
        result = detect_dependency_dirs(tmp_path)
        assert "vendor" not in result

    def test_deduplicates_across_lockfiles(self, tmp_path: Path) -> None:
        """Both composer.json and composer.lock imply vendor; should appear once."""
        _touch(tmp_path / "composer.json")
        _touch(tmp_path / "composer.lock")
        (tmp_path / "vendor").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert result.count("vendor") == 1

    def test_multiple_ecosystems(self, tmp_path: Path) -> None:
        _touch(tmp_path / "composer.json")
        _touch(tmp_path / "package.json")
        (tmp_path / "vendor").mkdir()
        (tmp_path / "node_modules").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert "vendor" in result
        assert "node_modules" in result

    def test_always_includes_git_when_present(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert ".git" in result

    def test_git_absent_not_included(self, tmp_path: Path) -> None:
        result = detect_dependency_dirs(tmp_path)
        assert ".git" not in result

    def test_empty_repo_no_results(self, tmp_path: Path) -> None:
        result = detect_dependency_dirs(tmp_path)
        assert result == []

    def test_result_has_no_duplicates(self, tmp_path: Path) -> None:
        _touch(tmp_path / "go.mod")
        _touch(tmp_path / "go.sum")
        (tmp_path / "vendor").mkdir()
        result = detect_dependency_dirs(tmp_path)
        assert len(result) == len(set(result))


class TestBuildExcludePathPrefixes:
    def test_single_dir(self) -> None:
        assert build_exclude_path_prefixes(["vendor"]) == ["/vendor/"]

    def test_multiple_dirs(self) -> None:
        result = build_exclude_path_prefixes(["vendor", "node_modules"])
        assert result == ["/vendor/", "/node_modules/"]

    def test_nested_dir(self) -> None:
        assert build_exclude_path_prefixes(["vendor/bundle"]) == ["/vendor/bundle/"]

    def test_dot_dir(self) -> None:
        assert build_exclude_path_prefixes([".git"]) == ["/.git/"]

    def test_empty_list(self) -> None:
        assert build_exclude_path_prefixes([]) == []

    def test_strips_leading_slash(self) -> None:
        assert build_exclude_path_prefixes(["/vendor"]) == ["/vendor/"]

    def test_strips_trailing_slash(self) -> None:
        assert build_exclude_path_prefixes(["vendor/"]) == ["/vendor/"]
