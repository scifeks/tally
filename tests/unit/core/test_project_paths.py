from pathlib import Path

from core.project_paths import ProjectPaths


class TestProjectPaths:
    def test_agentic_dir_returns_agentic_subdir(self, tmp_path: Path) -> None:
        paths = ProjectPaths(tmp_path)
        assert paths.agentic_dir == tmp_path / "agentic"

    def test_agentic_dir_is_consistent(self, tmp_path: Path) -> None:
        paths = ProjectPaths(tmp_path)
        assert paths.agentic_dir == paths.agentic_dir
