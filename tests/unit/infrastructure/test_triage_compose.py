"""Unit tests for infrastructure.docker.triage_compose."""

from __future__ import annotations

from pathlib import Path

from infrastructure.docker.triage_compose import (
    DockerTriageCompose,
)


class TestDockerTriageCompose:
    def test_writes_content_to_path(self, tmp_path: Path) -> None:
        compose_path = tmp_path / "docker-compose.yaml"
        writer = DockerTriageCompose()
        writer.write_compose_file(
            "services:\n  app:\n    image: test\n",
            compose_path,
        )
        assert compose_path.read_text() == ("services:\n  app:\n    image: test\n")

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        compose_path = tmp_path / "deep" / "nested" / "docker-compose.yaml"
        writer = DockerTriageCompose()
        writer.write_compose_file("content", compose_path)
        assert compose_path.exists()
        assert compose_path.read_text() == "content"
