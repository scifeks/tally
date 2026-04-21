"""Unit tests for infrastructure.tools.wrappers.utils.manifest_check."""

from __future__ import annotations

from unittest.mock import patch

from infrastructure.tools.wrappers.utils.manifest_check import (
    LANGUAGE_MANIFESTS,
    has_dependency_manifests,
    has_dependency_manifests_docker,
)


class TestHasDependencyManifests:
    def test_returns_true_when_manifest_exists(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), ["javascript"]) is True

    def test_returns_false_when_no_manifest_exists(self, tmp_path) -> None:
        assert has_dependency_manifests(str(tmp_path), ["javascript"]) is False

    def test_python_requirements_txt(self, tmp_path) -> None:
        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        assert has_dependency_manifests(str(tmp_path), ["python"]) is True

    def test_python_pyproject_toml(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\n")
        assert has_dependency_manifests(str(tmp_path), ["python"]) is True

    def test_python_pipfile(self, tmp_path) -> None:
        (tmp_path / "Pipfile").write_text("[packages]\n")
        assert has_dependency_manifests(str(tmp_path), ["python"]) is True

    def test_python_setup_py(self, tmp_path) -> None:
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")
        assert has_dependency_manifests(str(tmp_path), ["python"]) is True

    def test_python_setup_cfg(self, tmp_path) -> None:
        (tmp_path / "setup.cfg").write_text("[metadata]\n")
        assert has_dependency_manifests(str(tmp_path), ["python"]) is True

    def test_python_poetry_lock(self, tmp_path) -> None:
        (tmp_path / "poetry.lock").write_text("")
        assert has_dependency_manifests(str(tmp_path), ["python"]) is True

    def test_php_composer_json(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), ["php"]) is True

    def test_typescript_uses_package_json(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), ["typescript"]) is True

    def test_node_uses_package_json(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), ["node"]) is True

    def test_case_insensitive_language(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), ["JavaScript"]) is True

    def test_multiple_languages_returns_true_on_first_match(self, tmp_path) -> None:
        (tmp_path / "composer.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), ["python", "php"]) is True

    def test_multiple_languages_returns_false_when_none_match(self, tmp_path) -> None:
        assert has_dependency_manifests(str(tmp_path), ["python", "php"]) is False

    def test_empty_languages_returns_false(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text("{}")
        assert has_dependency_manifests(str(tmp_path), []) is False

    def test_unknown_language_returns_false(self, tmp_path) -> None:
        (tmp_path / "Gemfile").write_text("")
        assert has_dependency_manifests(str(tmp_path), ["ruby"]) is False

    def test_language_manifests_mapping_has_expected_keys(self) -> None:
        assert "javascript" in LANGUAGE_MANIFESTS
        assert "typescript" in LANGUAGE_MANIFESTS
        assert "node" in LANGUAGE_MANIFESTS
        assert "python" in LANGUAGE_MANIFESTS
        assert "php" in LANGUAGE_MANIFESTS


class TestHasDependencyManifestsDocker:
    def _mock_run_factory(self, returncode: int):
        """Return a mock subprocess.run that always returns a given returncode."""

        def _mock_run(cmd, **kwargs):
            result = type("R", (), {"returncode": returncode})()
            return result

        return _mock_run

    def test_returns_true_when_docker_test_succeeds(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.manifest_check.subprocess.run",
            side_effect=self._mock_run_factory(0),
        ):
            assert (
                has_dependency_manifests_docker("my-container", "/app", ["javascript"])
                is True
            )

    def test_returns_false_when_docker_test_fails(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.manifest_check.subprocess.run",
            side_effect=self._mock_run_factory(1),
        ):
            assert (
                has_dependency_manifests_docker("my-container", "/app", ["javascript"])
                is False
            )

    def test_returns_false_when_docker_exec_raises(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.manifest_check.subprocess.run",
            side_effect=OSError("docker not found"),
        ):
            assert (
                has_dependency_manifests_docker("my-container", "/app", ["python"])
                is False
            )

    def test_docker_test_invoked_with_correct_path(self) -> None:
        calls = []

        def _capture(cmd, **kwargs):
            calls.append(cmd)
            return type("R", (), {"returncode": 0})()

        with patch(
            "infrastructure.tools.wrappers.utils.manifest_check.subprocess.run",
            side_effect=_capture,
        ):
            has_dependency_manifests_docker("my-container", "/app", ["javascript"])

        assert len(calls) == 1
        assert calls[0] == [
            "docker",
            "exec",
            "my-container",
            "test",
            "-f",
            "/app/package.json",
        ]

    def test_trailing_slash_stripped_from_repo_path(self) -> None:
        calls = []

        def _capture(cmd, **kwargs):
            calls.append(cmd)
            return type("R", (), {"returncode": 0})()

        with patch(
            "infrastructure.tools.wrappers.utils.manifest_check.subprocess.run",
            side_effect=_capture,
        ):
            has_dependency_manifests_docker("my-container", "/app/", ["javascript"])

        assert "/app/package.json" in calls[0][-1]

    def test_returns_false_for_empty_languages(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.utils.manifest_check.subprocess.run"
        ) as mock_run:
            result = has_dependency_manifests_docker("c", "/app", [])
        assert result is False
        mock_run.assert_not_called()
