"""Tests for directory tree text generation."""

from pathlib import Path

from application.llm_scan.tree_shaker import build_tree


class TestBuildTree:
    def test_renders_files_and_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("x = 1")
        (tmp_path / "README.md").write_text("hello")

        result = build_tree(tmp_path, max_depth=3)
        assert "src/" in result
        assert "app.py" in result
        assert "README.md" in result

    def test_excludes_vendor_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "pkg.js").write_text("")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("")

        result = build_tree(tmp_path, max_depth=3)
        assert "node_modules" not in result
        assert "src/" in result

    def test_respects_max_depth(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "deep.py").write_text("")

        result = build_tree(tmp_path, max_depth=2)
        assert "deep.py" not in result

    def test_custom_excludes(self, tmp_path: Path) -> None:
        (tmp_path / "keep").mkdir()
        (tmp_path / "skip").mkdir()
        (tmp_path / "keep" / "a.py").write_text("")
        (tmp_path / "skip" / "b.py").write_text("")

        result = build_tree(
            tmp_path,
            max_depth=3,
            exclude_patterns={"skip"},
        )
        assert "keep/" in result
        assert "skip" not in result
