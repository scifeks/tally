"""Unit tests for URLMerger — scope filtering regression."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.wrappers.utils.url_merge import URLMerger


def _write_oas3(path: Path, paths: list[str]) -> None:
    """Write a minimal OAS3 file whose ``paths`` keys are *paths*."""
    path.write_text(
        json.dumps({"openapi": "3.0.0", "paths": {p: {} for p in paths}}),
        encoding="utf-8",
    )


class TestURLMergerScopeFilter:
    """URLMerger must drop URLs whose host:port differ from base_url."""

    def test_github_url_dropped_from_katana_oas3(self, tmp_path: Path) -> None:
        """Regression: out-of-scope Katana OAS3 entries must not appear in output."""
        base_path = tmp_path
        project = "test-project"
        repo = "dvwa"
        base_url = "http://dvwa.local"

        katana_dir = base_path / "projects" / project / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)

        _write_oas3(
            katana_dir / f"{repo}_20260101T000000_oas3.json",
            [
                # in-scope
                "http://dvwa.local/login.php",
                "/index.php",
                # out-of-scope — this is the regression case
                "https://github.com/digininja/DVWA/",
                "https://packagist.org/packages/some/pkg",
            ],
        )

        merger = URLMerger(
            base_path=str(base_path),
            project_name=project,
            repo_name=repo,
            base_url=base_url,
        )
        urls = merger.merge()

        assert all("github.com" not in u for u in urls), (
            f"github.com URL leaked into merged output: {urls}"
        )
        assert all("packagist.org" not in u for u in urls), (
            f"packagist.org URL leaked into merged output: {urls}"
        )
        # In-scope entries must survive
        assert any("dvwa.local" in u for u in urls), (
            f"Expected in-scope dvwa.local URLs to survive, got: {urls}"
        )

    def test_path_only_entries_joined_to_base(self, tmp_path: Path) -> None:
        """Path-only OAS3 keys are joined to base_url and kept."""
        base_path = tmp_path
        project = "proj"
        repo = "app"
        base_url = "http://localhost:3000"

        katana_dir = base_path / "projects" / project / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)
        _write_oas3(
            katana_dir / f"{repo}_20260101T000000_oas3.json",
            ["/api/users", "/api/items"],
        )

        merger = URLMerger(
            base_path=str(base_path),
            project_name=project,
            repo_name=repo,
            base_url=base_url,
        )
        urls = merger.merge()

        assert "http://localhost:3000/api/users" in urls
        assert "http://localhost:3000/api/items" in urls

    def test_empty_sources_returns_empty(self, tmp_path: Path) -> None:
        merger = URLMerger(
            base_path=str(tmp_path),
            project_name="proj",
            repo_name="repo",
            base_url="http://localhost",
        )
        assert merger.merge() == []
