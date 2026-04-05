"""Interactive project creation wizard for the tally REPL."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import Repository

if TYPE_CHECKING:
    from application.project.manager import ProjectManager

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\s\-]*$")

_REPO_TYPE_HELP = (
    "  Type  valid: library | api | ui\n"
    "        allowed combos: library  |  api  |  ui  |  api,ui\n"
    "        library is mutually exclusive; use commas for multiple types"
)

_LANG_INDICATORS = [
    (["*.py", "requirements.txt", "setup.py", "pyproject.toml"], "python"),
    (["*.js", "*.jsx", "*.ts", "*.tsx"], "javascript/typescript"),
    (["package.json"], "node"),
    (["*.php", "composer.json"], "php"),
    (["go.mod"], "go"),
    (["Gemfile"], "ruby"),
]

_TEST_DIR_NAMES: frozenset[str] = frozenset(
    {"test", "tests", "spec", "__tests__", "e2e"}
)


def _parse_repo_types(raw: str) -> list[str]:
    """Split comma-separated type input and strip whitespace."""
    return [t.strip() for t in raw.split(",") if t.strip()]


def _validate_repo_types(types: list[str]) -> str | None:
    """Return a user-facing error message, or None if types are valid."""
    if not types:
        return "Repository type is required."
    valid = {"library", "api", "ui"}
    invalid = set(types) - valid
    if invalid:
        bad = ", ".join(sorted(invalid))
        return f"Invalid type(s): {bad}. Valid values: library, api, ui"
    if "library" in types and len(types) > 1:
        return (
            "'library' is mutually exclusive and cannot be combined with other types."
        )
    return None


def _detect_test_dirs(repo_path: Path) -> list[str]:
    """Return sorted top-level subdir names that match known test dir names."""
    return sorted(
        e.name for e in repo_path.iterdir() if e.is_dir() and e.name in _TEST_DIR_NAMES
    )


def _detect_languages(repo_path: Path) -> list[str]:
    """Scan repo_path and return detected language names."""
    detected: list[str] = []
    for patterns, lang in _LANG_INDICATORS:
        for pattern in patterns:
            if list(repo_path.rglob(pattern)):
                detected.append(lang)
                break
    return detected


def _prompt(message: str, default: str = "") -> str:
    """Prompt user and return stripped input, falling back to default."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    return raw or default


class InteractiveProjectWizard:
    """Interactive terminal wizard for project and repository management."""

    def __init__(self, manager: ProjectManager) -> None:
        self._manager = manager

    def create_project(self) -> str | None:
        """Run interactive interview to create a new project.

        Returns:
            Created project name on success, None if user cancelled.
        """
        print("\nCreating new project...\n")
        try:
            name = self._interview_project_name()
            if name is None:
                return None

            repositories = self._interview_repositories()

            print("\nProject details:\n")
            company_name = self._interview_company_name()
            department_name = self._interview_department_name()
            abbreviation = self._interview_abbreviation()

            self._manager.create_project_dirs(name)
            self._manager.save_project(
                name, repositories, company_name, department_name, abbreviation
            )

            count = len(repositories)
            repo_str = f"{count} {'repository' if count == 1 else 'repositories'}"
            print(f"\n✓ Project '{name}' created with {repo_str}")
            self._manager.switch_project(name)

            return name

        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return None

    def add_repository(self, project_name: str) -> Repository | None:
        """Interactively add a repository to an existing project.

        Returns:
            Added Repository on success, None if cancelled.
        """
        if project_name not in self._manager.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        try:
            existing = self._manager.config.load_repositories(project_name)
            idx = len(existing) + 1
            print(f"\nAdding repository to project '{project_name}'...\n")
            repo = self._interview_single_repo(idx)
            if repo is None:
                return None
            existing.append(repo)
            self._manager.config.save_repositories(project_name, existing)
            print(f"\n✓ Repository '{repo.name}' added to project '{project_name}'")
            return repo
        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return None

    def edit_repository(self, project_name: str, repo_name: str) -> Repository | None:
        """Interactively edit an existing repository in project_name.

        Returns:
            Updated Repository on success, None if cancelled.

        Raises:
            ValueError: if the project or repository does not exist.
        """
        if project_name not in self._manager.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        repos = self._manager.config.load_repositories(project_name)
        idx = next((i for i, r in enumerate(repos) if r.name == repo_name), None)
        if idx is None:
            raise ValueError(f"Repository '{repo_name}' not found in '{project_name}'.")

        existing = repos[idx]
        print(
            f"\nEditing repository '{repo_name}'"
            " (press Enter to keep current value)...\n"
        )
        try:
            # Name
            while True:
                name = _prompt("  Name", default=existing.name)
                if name:
                    break
                print("  Repository name is required.")

            # Type
            print(_REPO_TYPE_HELP)
            current_type_str = ", ".join(existing.type) if existing.type else ""
            while True:
                type_input = _prompt("  Type", default=current_type_str)
                types = _parse_repo_types(type_input)
                err = _validate_repo_types(types)
                if err:
                    print(f"  {err}")
                    continue
                break

            # Mode selection
            current_mode_str = "docker" if existing.docker_path else "local"
            while True:
                mode = _prompt(
                    "  Mode [local/docker]", default=current_mode_str
                ).lower()
                if mode in ("local", "docker"):
                    break
                print("  Mode must be 'local' or 'docker'.")

            local_path_str = existing.path
            docker_path = ""
            container_name = ""
            if mode == "docker":
                container_name = _prompt(
                    "  Docker container name", default=existing.container_name
                ).strip()
                docker_path = _prompt(
                    "  Docker mount point", default=existing.docker_path
                ).strip()
                while True:
                    raw_path = _prompt(
                        "  Local path"
                        " (required for language detection and local tool execution)",
                        default=existing.path,
                    )
                    if not raw_path:
                        print("  Local path is required.")
                        continue
                    resolved = Path(raw_path).expanduser().resolve()
                    if not resolved.exists():
                        print(f"  Path does not exist: {raw_path}")
                        continue
                    local_path_str = str(resolved)
                    break
            else:
                while True:
                    raw_path = _prompt("  Local path", default=existing.path)
                    if not raw_path:
                        print("  Local path is required.")
                        continue
                    resolved = Path(raw_path).expanduser().resolve()
                    if not resolved.exists():
                        print(f"  Path does not exist: {raw_path}")
                        continue
                    local_path_str = str(resolved)
                    break

            # Languages
            detect_base = Path(local_path_str) if local_path_str else None
            detected = _detect_languages(detect_base) if detect_base else []
            if detected:
                detected_label = ", ".join(detected)
                prompt_label = f"  Languages (detected {detected_label})"
                default_langs = detected_label
            else:
                current_langs = (
                    ", ".join(existing.languages) if existing.languages else ""
                )
                prompt_label = "  Languages (comma-separated)"
                default_langs = current_langs
            lang_input = _prompt(prompt_label, default=default_langs)
            langs = [lang.strip() for lang in lang_input.split(",") if lang.strip()]

            # Dependencies file — pip-audit scope, only relevant for Python repos
            dependencies_file = existing.dependencies_file
            if "python" in [lang.lower() for lang in langs]:
                if mode == "docker":
                    print(
                        "  Note: if no dependencies file is provided, pip-audit will "
                        "scan all packages installed in the container environment."
                    )
                    dependencies_file = _prompt(
                        "  Python dependencies file"
                        " (container path, e.g. /app/requirements.txt, optional)",
                        default=existing.dependencies_file,
                    )
                else:
                    print(
                        "  Note: without a dependencies file, pip-audit will be "
                        "skipped for this repository."
                    )
                    dependencies_file = _prompt(
                        "  Python dependencies file"
                        " (local path, e.g. requirements.txt, optional)",
                        default=existing.dependencies_file,
                    )

            # Base URLs
            current_urls = ", ".join(existing.base_urls) if existing.base_urls else ""
            url_input = _prompt(
                "  Base URLs (comma-separated, optional)", default=current_urls
            )
            base_urls = [u.strip() for u in url_input.split(",") if u.strip()]

            # Test dir names
            detect_path = Path(local_path_str) if local_path_str else None
            auto_test_dirs = _detect_test_dirs(detect_path) if detect_path else []
            if auto_test_dirs:
                auto_label = ", ".join(auto_test_dirs)
                test_dirs_prompt = (
                    f"  Test dir names (detected {auto_label}, any depth)"
                )
                test_dirs_default = auto_label
            else:
                current_test = (
                    ", ".join(existing.test_dirs) if existing.test_dirs else ""
                )
                test_dirs_prompt = (
                    "  Test dir names (any depth, comma-separated, optional)"
                )
                test_dirs_default = current_test
            test_dirs_input = _prompt(test_dirs_prompt, default=test_dirs_default)
            test_dirs = [d.strip() for d in test_dirs_input.split(",") if d.strip()]

            # Ignore dir names
            current_ignore = (
                ", ".join(existing.ignore_dirs) if existing.ignore_dirs else ""
            )
            ignore_dirs_input = _prompt(
                "  Ignore dir names (e.g. vendor, node_modules, mocks"
                " — comma-separated, optional)",
                default=current_ignore,
            )
            ignore_dirs = [d.strip() for d in ignore_dirs_input.split(",") if d.strip()]

            updated = Repository(
                name=name,
                type=types,
                path=local_path_str,
                docker_path=docker_path,
                container_name=container_name,
                languages=langs,
                base_urls=base_urls,
                test_dirs=test_dirs,
                ignore_dirs=ignore_dirs,
                dependencies_file=dependencies_file,
            )
            repos[idx] = updated
            self._manager.config.save_repositories(project_name, repos)
            print(f"\n✓ Repository '{name}' updated")
            return updated

        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return None

    def _interview_company_name(self) -> str:
        """Prompt for a required company name."""
        while True:
            val = _prompt("  Company Name")
            if val:
                return val
            print("  Company Name is required.")

    def _interview_department_name(self) -> str:
        """Prompt for an optional department name."""
        return _prompt("  Department Name (optional)")

    def _interview_abbreviation(self) -> str:
        """Prompt for an optional project abbreviation (max 3 chars)."""
        while True:
            val = _prompt(
                "  Abbreviation"
                " (max 3 chars, used as finding prefix e.g. FOO-001, optional)"
            )
            if not val:
                return ""
            if len(val) > 3:
                print("  Abbreviation must be 3 characters or fewer.")
                continue
            return val

    def _interview_project_name(self) -> str | None:
        while True:
            name = _prompt("Project name")
            if not name:
                print("  Project name is required.")
                continue
            if not _NAME_RE.match(name):
                print(
                    "  Invalid name. Use letters, digits, spaces, and hyphens only "
                    "(must start with a letter or digit)."
                )
                continue
            if name in self._manager.list_projects():
                raise ValueError(f"Project '{name}' already exists.")
            return name

    def edit_project(self, project_name: str) -> bool:
        """Interactively edit project-level fields for *project_name*.

        Covers: company_name (required), department_name (optional),
        abbreviation (optional, max 3 chars).  Repositories are managed
        separately via ``repo add / edit / delete``.

        Returns:
            True on success, False if the user cancelled.

        Raises:
            ValueError: if the project does not exist.
        """
        config = self._manager.config.load_project_config(project_name)
        if config is None:
            raise ValueError(f"Project '{project_name}' not found.")

        print(
            f"\nEditing project '{project_name}'"
            " (press Enter to keep current value)...\n"
        )
        try:
            # Company Name — required
            while True:
                val = _prompt("  Company Name", default=config.company_name)
                if val:
                    company_name = val
                    break
                print("  Company Name is required.")

            # Department Name — optional
            department_name = _prompt(
                "  Department Name (optional)", default=config.department_name
            )

            # Abbreviation — keep / replace / clear
            current_abbrev = config.abbreviation
            if current_abbrev:
                hint = (
                    f"  Abbreviation [current: {current_abbrev},"
                    " enter --clear to remove]"
                )
            else:
                hint = (
                    "  Abbreviation"
                    " (max 3 chars, used as finding prefix e.g. FOO-001, optional)"
                )
            while True:
                val = _prompt(hint)
                if val == "--clear":
                    abbreviation = ""
                    break
                if not val:
                    abbreviation = current_abbrev  # keep existing
                    break
                if len(val) > 3:
                    print("  Abbreviation must be 3 characters or fewer.")
                    continue
                abbreviation = val
                break

            config.company_name = company_name
            config.department_name = department_name
            config.abbreviation = abbreviation
            self._manager.config.save_project_config(project_name, config)
            print(f"\n✓ Project '{project_name}' updated")
            return True

        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return False

    def _interview_repositories(self) -> list[Repository]:
        repositories: list[Repository] = []
        answer = _prompt("\nAdd repositories? [y/N]", default="N").lower()
        if answer not in ("y", "yes"):
            return repositories

        idx = 1
        while True:
            repo = self._interview_single_repo(idx)
            if repo is not None:
                repositories.append(repo)
                idx += 1

            again = _prompt("\n  Add another repository? [y/N]", default="N").lower()
            if again not in ("y", "yes"):
                break

        return repositories

    def _interview_single_repo(self, idx: int) -> Repository | None:
        print(f"\nRepository #{idx}:")

        # Name
        while True:
            name = _prompt("  Name")
            if name:
                break
            print("  Repository name is required.")

        # Type
        print(_REPO_TYPE_HELP)
        while True:
            type_input = _prompt("  Type")
            types = _parse_repo_types(type_input)
            err = _validate_repo_types(types)
            if err:
                print(f"  {err}")
                continue
            break

        # Mode selection
        while True:
            mode = _prompt("  Mode [local/docker]", default="local").lower()
            if mode in ("local", "docker"):
                break
            print("  Mode must be 'local' or 'docker'.")

        local_path_str = ""
        docker_path = ""
        container_name = ""
        if mode == "docker":
            while True:
                container_name = _prompt("  Docker container name").strip()
                if container_name:
                    break
                print("  Docker container name is required.")
            while True:
                docker_path = _prompt(
                    "  Docker mount point (path inside container)"
                ).strip()
                if docker_path:
                    break
                print("  Docker mount point is required.")
            while True:
                raw_path = _prompt(
                    "  Local path"
                    " (required for language detection and local tool execution)"
                )
                if not raw_path:
                    print("  Local path is required.")
                    continue
                resolved = Path(raw_path).expanduser().resolve()
                if not resolved.exists():
                    print(f"  Path does not exist: {raw_path}")
                    continue
                local_path_str = str(resolved)
                break
        else:
            while True:
                raw_path = _prompt("  Local path")
                if not raw_path:
                    print("  Local path is required.")
                    continue
                resolved = Path(raw_path).expanduser().resolve()
                if not resolved.exists():
                    print(f"  Path does not exist: {raw_path}")
                    continue
                local_path_str = str(resolved)
                break

        # Languages
        detect_base = Path(local_path_str) if local_path_str else None
        detected = _detect_languages(detect_base) if detect_base else []
        if detected:
            detected_label = ", ".join(detected)
            prompt_label = f"  Languages (detected {detected_label})"
            default_langs = detected_label
        else:
            prompt_label = "  Languages (comma-separated)"
            default_langs = ""
        lang_input = _prompt(prompt_label, default=default_langs)
        langs = [lang.strip() for lang in lang_input.split(",") if lang.strip()]

        # Dependencies file — pip-audit scope, only relevant for Python repos
        dependencies_file = ""
        if "python" in [lang.lower() for lang in langs]:
            if mode == "docker":
                print(
                    "  Note: if no dependencies file is provided, pip-audit will "
                    "scan all packages installed in the container environment."
                )
                dependencies_file = _prompt(
                    "  Python dependencies file"
                    " (container path, e.g. /app/requirements.txt, optional)"
                )
            else:
                print(
                    "  Note: without a dependencies file, pip-audit will be "
                    "skipped for this repository."
                )
                dependencies_file = _prompt(
                    "  Python dependencies file"
                    " (local path, e.g. requirements.txt, optional)"
                )

        # Base URLs
        url_input = _prompt("  Base URLs (comma-separated, optional)")
        base_urls = [u.strip() for u in url_input.split(",") if u.strip()]

        # Test dir names
        detect_path = Path(local_path_str) if local_path_str else None
        auto_test_dirs = _detect_test_dirs(detect_path) if detect_path else []
        if auto_test_dirs:
            auto_label = ", ".join(auto_test_dirs)
            test_dirs_prompt = f"  Test dir names (detected {auto_label}, any depth)"
            test_dirs_default = auto_label
        else:
            test_dirs_prompt = "  Test dir names (any depth, comma-separated, optional)"
            test_dirs_default = ""
        test_dirs_input = _prompt(test_dirs_prompt, default=test_dirs_default)
        test_dirs = [d.strip() for d in test_dirs_input.split(",") if d.strip()]

        # Ignore dir names
        ignore_dirs_input = _prompt(
            "  Ignore dir names (e.g. vendor, node_modules, mocks"
            " — comma-separated, optional)"
        )
        ignore_dirs = [d.strip() for d in ignore_dirs_input.split(",") if d.strip()]

        return Repository(
            name=name,
            type=types,
            path=local_path_str,
            docker_path=docker_path,
            container_name=container_name,
            languages=langs,
            base_urls=base_urls,
            test_dirs=test_dirs,
            ignore_dirs=ignore_dirs,
            dependencies_file=dependencies_file,
        )
