"""Scanner for finding route and controller files in a repository."""

from __future__ import annotations

from pathlib import Path


def find_route_files(
    repo_path: str, excluded_dirs: list[str] | None = None, max_files: int = 50
) -> list[Path]:
    """Find files likely to contain route definitions or controller actions."""
    repo = Path(repo_path)
    if not repo.exists() or not repo.is_dir():
        return []

    excluded_dirs = excluded_dirs or []
    excluded_dirs_lower = {d.lower() for d in excluded_dirs}

    built_in_excluded = {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        "target",
        ".idea",
        ".vscode",
        "bower_components",
        ".next",
        ".svn",
        "storage",
        "cache",
        "migrations",
        "tests",
        "test",
        "spec",
        "fixtures",
    }

    non_route_dirs = {
        "model",
        "models",
        "entity",
        "entities",
        "migration",
        "migrations",
        "seeder",
        "seeders",
        "factory",
        "factories",
        "middleware",
        "config",
        "database",
        "lang",
        "resources",
        "storage",
        "public",
        "assets",
        "css",
        "js",
        "images",
        "fonts",
        "sass",
        "less",
        "translations",
    }

    source_extensions = {
        ".php",
        ".py",
        ".js",
        ".ts",
        ".rb",
        ".java",
        ".go",
        ".rs",
        ".cs",
        ".kt",
    }

    route_stem_names = {"routes", "web", "api", "urls", "router"}

    route_keywords = {"controller", "action", "handler", "endpoint"}

    route_dir_names = {
        "actions",
        "controllers",
        "controller",
        "routes",
        "handlers",
        "endpoints",
        "views",
        "api",
    }

    found_files: list[Path] = []

    for file_path in repo.rglob("*"):
        if len(found_files) >= max_files:
            break

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in source_extensions:
            continue

        path_parts_lower = {p.lower() for p in file_path.parts}

        if any(part in excluded_dirs_lower for part in path_parts_lower):
            continue

        if any(part in built_in_excluded for part in path_parts_lower):
            continue

        if any(part in non_route_dirs for part in path_parts_lower):
            continue

        is_route_file = False

        parent_parts_lower = {p.lower() for p in file_path.parent.parts}
        if any(part in route_dir_names for part in parent_parts_lower):
            is_route_file = True

        stem_lower = file_path.stem.lower()
        if stem_lower in route_stem_names:
            is_route_file = True

        if any(keyword in stem_lower for keyword in route_keywords):
            is_route_file = True

        if is_route_file:
            found_files.append(file_path)

    return found_files
