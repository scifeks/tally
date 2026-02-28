"""Project management for tally pentesting REPL."""
#todo: Keep an eye on file size here. consider modular approach.
import datetime
import json
import re
from pathlib import Path
from typing import List, Optional

from core.config import ConfigManager, ProjectConfig, Repository, NmapProfile


_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')

_LANG_INDICATORS = [
    (['*.py', 'requirements.txt', 'setup.py', 'pyproject.toml'], 'python'),
    (['*.js', '*.jsx', '*.ts', '*.tsx'], 'javascript/typescript'),
    (['package.json'], 'node'),
    (['*.php', 'composer.json'], 'php'),
    (['go.mod'], 'go'),
    (['Gemfile'], 'ruby'),
]


def _detect_languages(repo_path: Path) -> List[str]:
    """Scan repo_path and return detected language names."""
    detected: List[str] = []
    for patterns, lang in _LANG_INDICATORS:
        for pattern in patterns:
            if list(repo_path.rglob(pattern)):
                detected.append(lang)
                break
    return detected


def _prompt(message: str, default: str = '') -> str:
    """Prompt user and return stripped input, falling back to default."""
    suffix = f' [{default}]' if default else ''
    raw = input(f'{message}{suffix}: ').strip()
    return raw or default


class ProjectManager:
    """Manages tally projects: creation, listing, switching, and repositories."""

    def __init__(self, base_path: str = '.'):
        self.base_path = Path(base_path)
        self.projects_dir = self.base_path / 'projects'
        self.active_file = self.projects_dir / '.active'
        self.config = ConfigManager(base_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_projects(self) -> List[str]:
        """Return sorted list of project names found in projects/."""
        if not self.projects_dir.exists():
            return []
        return sorted(
            d.name
            for d in self.projects_dir.iterdir()
            if d.is_dir() and not d.name.startswith('.')
            and (d / 'config' / 'project.json').exists()
        )

    def get_active_project(self) -> Optional[str]:
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

    def get_project_info(self, project_name: str) -> Optional[ProjectConfig]:
        """Load and return ProjectConfig for project_name."""
        return self.config.load_project_config(project_name)

    def create_project(self) -> Optional[str]:
        """Run interactive interview to create a new project.

        Returns:
            Created project name on success, None if user cancelled.
        """
        print('\nCreating new project...\n')
        try:
            name = self._interview_project_name()
            if name is None:
                return None

            repositories = self._interview_repositories()

            self._create_project_dirs(name)
            self._save_project(name, repositories)

            count = len(repositories)
            repo_str = f'{count} {"repository" if count == 1 else "repositories"}'
            print(f"\n✓ Project '{name}' created with {repo_str}")
            self.switch_project(name)
            return name

        except KeyboardInterrupt:
            print('\n\n[Cancelled]')
            return None

    def add_repository(self, project_name: str) -> Optional[Repository]:
        """Interactively add a repository to an existing project.

        Returns:
            Added Repository on success, None if cancelled.
        """
        if project_name not in self.list_projects():
            raise ValueError(f"Project '{project_name}' does not exist.")
        try:
            existing = self.config.load_repositories(project_name)
            idx = len(existing) + 1
            print(f'\nAdding repository to project \'{project_name}\'...\n')
            repo = self._interview_single_repo(idx)
            if repo is None:
                return None
            existing.append(repo)
            self.config.save_repositories(project_name, existing)
            print(f"\n✓ Repository '{repo.name}' added to project '{project_name}'")
            return repo
        except KeyboardInterrupt:
            print('\n\n[Cancelled]')
            return None

    # ------------------------------------------------------------------
    # Interview helpers
    # ------------------------------------------------------------------

    def _interview_project_name(self) -> Optional[str]:
        while True:
            name = _prompt('Project name')
            if not name:
                print('  Project name is required.')
                continue
            if not _NAME_RE.match(name):
                print(
                    '  Invalid name. Use lowercase letters, digits, and hyphens only '
                    '(must start with a letter or digit).'
                )
                continue
            if name in self.list_projects():
                raise ValueError(f"Project '{name}' already exists.")
            return name

    def _interview_repositories(self) -> List[Repository]:
        repositories: List[Repository] = []
        answer = _prompt('\nAdd repositories? [y/N]', default='N').lower()
        if answer not in ('y', 'yes'):
            return repositories

        idx = 1
        while True:
            repo = self._interview_single_repo(idx)
            if repo is not None:
                repositories.append(repo)
                idx += 1

            again = _prompt('\n  Add another repository? [y/N]', default='N').lower()
            if again not in ('y', 'yes'):
                break

        return repositories

    def _interview_single_repo(self, idx: int) -> Optional[Repository]:
        print(f'\nRepository #{idx}:')

        # Name
        while True:
            name = _prompt('  Name')
            if name:
                break
            print('  Repository name is required.')

        # Path
        while True:
            raw_path = _prompt('  Path')
            if not raw_path:
                print('  Path is required.')
                continue
            repo_path = Path(raw_path).expanduser().resolve()
            if repo_path.exists():
                break
            print(f"  Path does not exist: {raw_path}")

        # Languages
        lang_input = _prompt("  Languages (comma-separated or 'auto')")
        if lang_input.lower() == 'auto':
            langs = _detect_languages(repo_path)
            if langs:
                print(f'  [Detected: {", ".join(langs)}]')
            else:
                print('  [No languages detected]')
        else:
            langs = [l.strip() for l in lang_input.split(',') if l.strip()]

        # Base URLs
        url_input = _prompt('  Base URLs (comma-separated, optional)')
        base_urls = [u.strip() for u in url_input.split(',') if u.strip()]

        return Repository(
            name=name,
            path=str(repo_path),
            languages=langs,
            base_urls=base_urls,
        )

    # ------------------------------------------------------------------
    # Filesystem helpers
    # ------------------------------------------------------------------

    def _create_project_dirs(self, name: str) -> None:
        project_root = self.projects_dir / name
        dirs = [
            project_root / 'config' / 'endpoints',
            project_root / 'chroma_db',
            project_root / 'tool_outputs' / 'nmap',
            project_root / 'tool_outputs' / 'semgrep',
            project_root / 'tool_outputs' / 'osv-scanner',
            project_root / 'tool_outputs' / 'gitleaks',
            project_root / 'tool_outputs' / 'zap',
            project_root / 'sessions',
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

        nmap_hosts = project_root / 'config' / 'nmap_hosts.json'
        if not nmap_hosts.exists():
            nmap_hosts.write_text('{}')

    def _save_project(self, name: str, repositories: List[Repository]) -> None:
        project_cfg = ProjectConfig(
            project_name=name,
            created=datetime.datetime.now().isoformat(),
            repositories=repositories,
        )
        self.config.save_project_config(name, project_cfg)
        self.config.save_repositories(name, repositories)
