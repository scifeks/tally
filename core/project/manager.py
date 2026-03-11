"""Project management for tally Security Auditing REPL."""

# todo: Keep an eye on file size here. consider modular approach.
import datetime
import re
import shutil
from pathlib import Path

from core.config import ConfigManager, ProjectConfig, Repository

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\s\-]*$")

_REPO_TYPE_HELP = (
    "  Type  valid: library | api | ui\n"
    "        allowed combos: library  |  api  |  ui  |  api,ui\n"
    "        library is mutually exclusive; use commas for multiple types"
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


_LANG_INDICATORS = [
    (["*.py", "requirements.txt", "setup.py", "pyproject.toml"], "python"),
    (["*.js", "*.jsx", "*.ts", "*.tsx"], "javascript/typescript"),
    (["package.json"], "node"),
    (["*.php", "composer.json"], "php"),
    (["go.mod"], "go"),
    (["Gemfile"], "ruby"),
]


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


class ProjectManager:
    """Manages tally projects: creation, listing, switching, and repositories."""

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.projects_dir = self.base_path / "projects"
        self.active_file = self.projects_dir / ".active"
        self.config = ConfigManager(base_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_projects(self) -> list[str]:
        """Return sorted list of project names found in projects/."""
        if not self.projects_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.projects_dir.iterdir()
            if d.is_dir()
            and not d.name.startswith(".")
            and (d / "config" / "project.json").exists()
        )

    def get_active_project(self) -> str | None:
        """Return the currently active project name, or None."""
        if not self.active_file.exists():
            return None
        name = self.active_file.read_text().strip()
        return name if name else None

    def switch_project(self, project_name: str) -> None:
        """Set project_name as the active project.

        Raises:
            ValueError: if the project does not exist.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.active_file.write_text(project_name)

    def get_project_info(self, project_name: str) -> ProjectConfig | None:
        """Load and return ProjectConfig for project_name."""
        return self.config.load_project_config(project_name)

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

            self._create_project_dirs(name)
            self._save_project(name, repositories)

            count = len(repositories)
            repo_str = f"{count} {'repository' if count == 1 else 'repositories'}"
            print(f"\n✓ Project '{name}' created with {repo_str}")
            self.switch_project(name)

            try:
                from core.setup.nmap_setup import interview_nmap_config

                interview_nmap_config(name, str(self.base_path))
            except KeyboardInterrupt:
                print("\n\n[Nmap config skipped]")

            return name

        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return None

    def add_repository(self, project_name: str) -> Repository | None:
        """Interactively add a repository to an existing project.

        Returns:
            Added Repository on success, None if cancelled.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        try:
            existing = self.config.load_repositories(project_name)
            idx = len(existing) + 1
            print(f"\nAdding repository to project '{project_name}'...\n")
            repo = self._interview_single_repo(idx)
            if repo is None:
                return None
            existing.append(repo)
            self.config.save_repositories(project_name, existing)
            print(f"\n✓ Repository '{repo.name}' added to project '{project_name}'")
            return repo
        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return None

    # ------------------------------------------------------------------
    # Interview helpers
    # ------------------------------------------------------------------

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
            if name in self.list_projects():
                raise ValueError(f"Project '{name}' already exists.")
            return name

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

        # Path + Docker path (at least one required)
        local_path_str = ""
        docker_path = ""
        while True:
            raw_path = _prompt("  Path (local filesystem, leave blank if docker-only)")
            raw_docker = _prompt(
                "  Docker path (container mount point, leave blank if local-only)"
            )

            if not raw_path and not raw_docker:
                print("  At least one of path or docker_path is required.")
                continue

            if raw_path:
                resolved = Path(raw_path).expanduser().resolve()
                if not resolved.exists():
                    print(f"  Path does not exist: {raw_path}")
                    continue
                local_path_str = str(resolved)

            docker_path = raw_docker.strip()
            break

        # Container name (only relevant when docker_path is set)
        container_name = ""
        if docker_path:
            container_name = _prompt("  Docker container name").strip()

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

        # Base URLs
        url_input = _prompt("  Base URLs (comma-separated, optional)")
        base_urls = [u.strip() for u in url_input.split(",") if u.strip()]

        return Repository(
            name=name,
            type=types,
            path=local_path_str,
            docker_path=docker_path,
            container_name=container_name,
            languages=langs,
            base_urls=base_urls,
        )

    def edit_repository(self, project_name: str, repo_name: str) -> Repository | None:
        """Interactively edit an existing repository in project_name.

        Returns:
            Updated Repository on success, None if cancelled.

        Raises:
            ValueError: if the project or repository does not exist.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        repos = self.config.load_repositories(project_name)
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

            # Path + Docker path (at least one required)
            local_path_str = existing.path
            docker_path = existing.docker_path
            while True:
                raw_path = _prompt("  Path (local filesystem)", default=existing.path)
                raw_docker = _prompt(
                    "  Docker path (container mount point)",
                    default=existing.docker_path,
                )

                if not raw_path and not raw_docker:
                    print("  At least one of path or docker_path is required.")
                    continue

                if raw_path:
                    resolved = Path(raw_path).expanduser().resolve()
                    if not resolved.exists():
                        print(f"  Path does not exist: {raw_path}")
                        continue
                    local_path_str = str(resolved)
                else:
                    local_path_str = ""

                docker_path = raw_docker.strip()
                break

            # Container name (only relevant when docker_path is set)
            container_name = existing.container_name
            if docker_path:
                container_name = _prompt(
                    "  Docker container name", default=existing.container_name
                ).strip()

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

            # Base URLs
            current_urls = ", ".join(existing.base_urls) if existing.base_urls else ""
            url_input = _prompt(
                "  Base URLs (comma-separated, optional)", default=current_urls
            )
            base_urls = [u.strip() for u in url_input.split(",") if u.strip()]

            updated = Repository(
                name=name,
                type=types,
                path=local_path_str,
                docker_path=docker_path,
                container_name=container_name,
                languages=langs,
                base_urls=base_urls,
            )
            repos[idx] = updated
            self.config.save_repositories(project_name, repos)
            print(f"\n✓ Repository '{name}' updated")
            return updated

        except KeyboardInterrupt:
            print("\n\n[Cancelled]")
            return None

    def delete_project(self, project_name: str) -> None:
        """Delete a project and all its data from disk.

        Raises:
            ValueError: If the project does not exist.
        """
        project_dir = self.projects_dir / project_name
        if not project_dir.exists():
            raise ValueError(f"Project '{project_name}' not found.")
        shutil.rmtree(project_dir)

        # Clear .active file if it points to the deleted project
        active_file = self.projects_dir / ".active"
        if active_file.exists():
            try:
                current = active_file.read_text().strip()
                if current == project_name:
                    active_file.unlink()
            except OSError:
                pass

    def delete_repository(self, project_name: str, repo_name: str) -> None:
        """Remove a repository from project_name by name.

        Raises:
            ValueError: if the project or repository does not exist.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        repos = self.config.load_repositories(project_name)
        new_repos = [r for r in repos if r.name != repo_name]
        if len(new_repos) == len(repos):
            raise ValueError(f"Repository '{repo_name}' not found in '{project_name}'.")
        self.config.save_repositories(project_name, new_repos)

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------

    def _create_project_dirs(self, name: str) -> None:
        project_root = self.projects_dir / name
        dirs = [
            project_root / "config" / "endpoints",
            project_root / "chroma_db",
            project_root / "tool_outputs" / "nmap",
            project_root / "tool_outputs" / "semgrep",
            project_root / "tool_outputs" / "osv-scanner",
            project_root / "tool_outputs" / "pip-audit",
            project_root / "tool_outputs" / "npm-audit",
            project_root / "tool_outputs" / "composer-audit",
            project_root / "tool_outputs" / "gitleaks",
            project_root / "tool_outputs" / "zap",
            project_root / "sessions",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        nmap_hosts = project_root / "config" / "nmap_hosts.json"
        if not nmap_hosts.exists():
            nmap_hosts.write_text("{}")

    def _save_project(self, name: str, repositories: list[Repository]) -> None:
        project_cfg = ProjectConfig(
            project_name=name,
            created=datetime.datetime.now().isoformat(),
            repositories=repositories,
        )
        self.config.save_project_config(name, project_cfg)
