"""Tests for Repository schema validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas import Repository  # noqa: E402
from core.config.schemas.repo_service import RepoService  # noqa: E402

pytestmark = pytest.mark.integration


def _make_repo(**kwargs: object) -> Repository:
    service_kwargs: dict[str, object] = {
        "name": "default",
        "type": ["api"],
        "languages": ["python"],
    }
    repo_kwargs: dict[str, object] = {
        "name": "test-repo",
        "path": str(_TALLY_ROOT),
    }
    for key in list(kwargs.keys()):
        if key in ("type", "languages", "docker_path", "container_name"):
            service_kwargs[key] = kwargs.pop(key)
    repo_kwargs.update(kwargs)
    repo_kwargs["services"] = [service_kwargs]
    return Repository(**repo_kwargs)  # type: ignore[arg-type]


class TestRepositoryTypeSchema:
    def test_valid_api(self) -> None:
        repo = _make_repo(type=["api"])
        assert repo.services[0].type == ["api"]

    def test_valid_ui(self) -> None:
        repo = _make_repo(type=["ui"])
        assert repo.services[0].type == ["ui"]

    def test_valid_library(self) -> None:
        repo = _make_repo(type=["library"])
        assert repo.services[0].type == ["library"]

    def test_valid_api_ui(self) -> None:
        repo = _make_repo(type=["api", "ui"])
        assert repo.services[0].type == ["api", "ui"]

    def test_missing_type_defaults_to_empty(self) -> None:
        repo = Repository(
            name="r",
            path=str(_TALLY_ROOT),
            services=[RepoService(name="default")],
        )
        assert repo.services[0].type == []

    def test_empty_type_is_valid(self) -> None:
        repo = _make_repo(type=[])
        assert repo.services[0].type == []

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid"):
            _make_repo(type=["backend"])

    def test_library_with_api_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "api"])

    def test_library_with_ui_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "ui"])

    def test_docker_only_repo_valid(self) -> None:
        repo = _make_repo(path="", docker_path="/mnt/repo", container_name="c")
        assert repo.services[0].docker_path == "/mnt/repo"
        assert repo.path == ""

    def test_docker_path_requires_container_name(self) -> None:
        with pytest.raises(Exception, match="container_name"):
            _make_repo(docker_path="/mnt/repo", container_name="")

    def test_valid_docker_repo(self) -> None:
        repo = _make_repo(docker_path="/mnt/repo", container_name="my-container")
        assert repo.services[0].docker_path == "/mnt/repo"
        assert repo.services[0].container_name == "my-container"

    def test_valid_local_repo(self) -> None:
        repo = _make_repo()
        assert repo.path == str(_TALLY_ROOT)
        assert repo.services[0].docker_path == ""
