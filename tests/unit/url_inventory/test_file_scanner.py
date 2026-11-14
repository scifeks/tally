"""Unit tests for route file scanner."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.url_inventory.file_scanner import find_route_files


@pytest.fixture
def repo_tree(tmp_path: Path) -> Path:
    """Create a test repository tree."""
    (tmp_path / "app" / "Actions").mkdir(parents=True)
    (tmp_path / "app" / "Actions" / "ListCustomers.php").write_text("")
    (tmp_path / "app" / "Actions" / "CreateOrder.php").write_text("")

    (tmp_path / "routes").mkdir(parents=True)
    (tmp_path / "routes" / "web.php").write_text("")

    (tmp_path / "src" / "Model").mkdir(parents=True)
    (tmp_path / "src" / "Model" / "User.php").write_text("")

    (tmp_path / "vendor" / "lib").mkdir(parents=True)
    (tmp_path / "vendor" / "lib" / "Route.php").write_text("")

    (tmp_path / "README.md").write_text("")

    return tmp_path


class TestFindRouteFiles:
    def test_finds_controller_and_route_files(self, repo_tree: Path) -> None:
        result = find_route_files(str(repo_tree))
        result_names = {f.name for f in result}

        assert "ListCustomers.php" in result_names
        assert "CreateOrder.php" in result_names
        assert "web.php" in result_names

    def test_excludes_vendor_directories(self, repo_tree: Path) -> None:
        result = find_route_files(str(repo_tree), excluded_dirs=["vendor"])
        result_names = {f.name for f in result}

        assert "Route.php" not in result_names

    def test_excludes_non_source_files(self, repo_tree: Path) -> None:
        result = find_route_files(str(repo_tree))
        result_names = {f.name for f in result}

        assert "README.md" not in result_names

    def test_skips_model_files(self, repo_tree: Path) -> None:
        result = find_route_files(str(repo_tree))
        result_names = {f.name for f in result}

        assert "User.php" not in result_names

    def test_respects_max_files(self, repo_tree: Path) -> None:
        result = find_route_files(str(repo_tree), max_files=2)
        assert len(result) <= 2

    def test_empty_repo(self, tmp_path: Path) -> None:
        result = find_route_files(str(tmp_path))
        assert result == []

    def test_nonexistent_path(self) -> None:
        result = find_route_files("/nonexistent/path")
        assert result == []

    def test_returns_path_objects(self, repo_tree: Path) -> None:
        result = find_route_files(str(repo_tree))
        assert all(isinstance(p, Path) for p in result)

    def test_only_includes_source_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "app" / "Controllers").mkdir(parents=True)
        (tmp_path / "app" / "Controllers" / "Home.php").write_text("")
        (tmp_path / "app" / "Controllers" / "config.json").write_text("")
        (tmp_path / "app" / "Controllers" / "script.sh").write_text("")

        result = find_route_files(str(tmp_path))
        result_names = {f.name for f in result}

        assert "Home.php" in result_names
        assert "config.json" not in result_names
        assert "script.sh" not in result_names

    def test_recognizes_route_stem_names(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "app" / "routes.py").write_text("")
        (tmp_path / "app" / "web.ts").write_text("")
        (tmp_path / "app" / "api.js").write_text("")
        (tmp_path / "app" / "urls.rb").write_text("")
        (tmp_path / "app" / "router.go").write_text("")

        result = find_route_files(str(tmp_path))
        result_names = {f.name for f in result}

        assert "routes.py" in result_names
        assert "web.ts" in result_names
        assert "api.js" in result_names
        assert "urls.rb" in result_names
        assert "router.go" in result_names

    def test_recognizes_controller_handler_endpoint_in_stem(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "app" / "UserController.php").write_text("")
        (tmp_path / "app" / "LoginAction.java").write_text("")
        (tmp_path / "app" / "AuthHandler.py").write_text("")
        (tmp_path / "app" / "ApiEndpoint.cs").write_text("")

        result = find_route_files(str(tmp_path))
        result_names = {f.name for f in result}

        assert "UserController.php" in result_names
        assert "LoginAction.java" in result_names
        assert "AuthHandler.py" in result_names
        assert "ApiEndpoint.cs" in result_names

    def test_respects_additional_excluded_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "app" / "Controllers").mkdir(parents=True)
        (tmp_path / "app" / "Controllers" / "Home.php").write_text("")
        (tmp_path / "custom_skip").mkdir(parents=True)
        (tmp_path / "custom_skip" / "routes.py").write_text("")

        result = find_route_files(str(tmp_path), excluded_dirs=["custom_skip"])
        result_names = {f.name for f in result}

        assert "Home.php" in result_names
        assert "routes.py" not in result_names

    def test_case_insensitive_directory_matching(self, tmp_path: Path) -> None:
        (tmp_path / "app" / "CONTROLLERS").mkdir(parents=True)
        (tmp_path / "app" / "CONTROLLERS" / "Home.php").write_text("")
        (tmp_path / "app" / "Actions").mkdir(parents=True)
        (tmp_path / "app" / "Actions" / "Create.php").write_text("")

        result = find_route_files(str(tmp_path))
        result_names = {f.name for f in result}

        assert "Home.php" in result_names
        assert "Create.php" in result_names

    def test_case_insensitive_stem_matching(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir(parents=True)
        (tmp_path / "app" / "ROUTES.py").write_text("")
        (tmp_path / "app" / "Api.js").write_text("")

        result = find_route_files(str(tmp_path))
        result_names = {f.name for f in result}

        assert "ROUTES.py" in result_names
        assert "Api.js" in result_names

    def test_skips_multiple_excluded_directories(self, tmp_path: Path) -> None:
        (tmp_path / "app" / "Controllers").mkdir(parents=True)
        (tmp_path / "app" / "Controllers" / "Home.php").write_text("")
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "routes.js").write_text("")
        (tmp_path / ".git" / "objects").mkdir(parents=True)
        (tmp_path / ".git" / "objects" / "api.py").write_text("")

        result = find_route_files(str(tmp_path))
        result_names = {f.name for f in result}

        assert "Home.php" in result_names
        assert "routes.js" not in result_names
        assert "api.py" not in result_names
