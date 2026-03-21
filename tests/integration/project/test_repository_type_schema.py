"""Tests for Repository schema validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas import Repository  # noqa: E402

pytestmark = pytest.mark.integration


def _make_repo(**kwargs: object) -> Repository:
    defaults: dict[str, object] = {
        "name": "test-repo",
        "type": ["api"],
        "path": str(_TALLY_ROOT),
        "languages": ["python"],
    }
    defaults.update(kwargs)
    return Repository(**defaults)  # type: ignore[arg-type]


class TestRepositoryTypeSchema:
    def test_valid_api(self) -> None:
        repo = _make_repo(type=["api"])
        assert repo.type == ["api"]

    def test_valid_ui(self) -> None:
        repo = _make_repo(type=["ui"])
        assert repo.type == ["ui"]

    def test_valid_library(self) -> None:
        repo = _make_repo(type=["library"])
        assert repo.type == ["library"]

    def test_valid_api_ui(self) -> None:
        repo = _make_repo(type=["api", "ui"])
        assert repo.type == ["api", "ui"]

    def test_missing_type_raises(self) -> None:
        with pytest.raises(Exception):
            Repository(  # type: ignore[call-arg]
                name="r",
                path=str(_TALLY_ROOT),
                languages=[],
            )

    def test_empty_type_raises(self) -> None:
        with pytest.raises(Exception):
            _make_repo(type=[])

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid"):
            _make_repo(type=["backend"])

    def test_library_with_api_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "api"])

    def test_library_with_ui_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "ui"])

    def test_no_paths_raises(self) -> None:
        with pytest.raises(Exception, match="path"):
            _make_repo(path="", docker_path="")

    def test_docker_only_repo_valid(self) -> None:
        # Existing docker-only repos (no local path) must still load without error
        repo = _make_repo(path="", docker_path="/mnt/repo", container_name="c")
        assert repo.docker_path == "/mnt/repo"
        assert repo.path == ""

    def test_docker_path_requires_container_name(self) -> None:
        with pytest.raises(Exception, match="container_name"):
            _make_repo(docker_path="/mnt/repo", container_name="")

    def test_valid_docker_repo(self) -> None:
        repo = _make_repo(docker_path="/mnt/repo", container_name="my-container")
        assert repo.docker_path == "/mnt/repo"
        assert repo.container_name == "my-container"

    def test_valid_local_repo(self) -> None:
        repo = _make_repo()
        assert repo.path == str(_TALLY_ROOT)
        assert repo.docker_path == ""
