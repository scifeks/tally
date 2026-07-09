"""Unit tests for repository CLI commands."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from application.cli.commands.repo import (
    cmd_repo_add,
    cmd_repo_delete,
    cmd_repo_edit,
    cmd_repo_list,
)
from application.cli.exit_codes import (
    INVALID_ARGS,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.project.repositories_service import DuplicateRepositoryName
from core.config import Repository
from core.config.schemas.repo_service import RepoService


def _create_mock_repo(
    name: str = "test-repo",
    repo_id: int = 1,
    path: str | None = None,
) -> Repository:
    """Create a mock Repository instance with a temporary path."""
    if path is None:
        path = tempfile.mkdtemp()

    repo = Repository(
        name=name,
        path=path,
        services=[RepoService(name="default", type=["api"], languages=["php"])],
    )
    return repo.model_copy(update={"id": repo_id})


def _create_mock_args(
    project: str | None = "test-project",
    repo_name: str | None = None,
    repo_path: str | None = None,
    languages: str | None = None,
    repo_type: str | None = None,
    base_urls: str | None = None,
    graphql_paths: str | None = None,
    container_name: str | None = None,
    docker_path: str | None = None,
    dependencies_file: str | None = None,
    test_dirs: str | None = None,
    ignore_dirs: str | None = None,
    no_crawl: bool = False,
    psalm_stubs: str | None = None,
    graphql_cop_headers: str | None = None,
) -> MagicMock:
    """Create a mock Namespace with repo command args."""
    args = MagicMock()
    args.project = project
    args.repo_name = repo_name
    args.repo_path = repo_path
    args.languages = languages
    args.repo_type = repo_type
    args.base_urls = base_urls
    args.graphql_paths = graphql_paths
    args.container_name = container_name
    args.docker_path = docker_path
    args.dependencies_file = dependencies_file
    args.test_dirs = test_dirs
    args.ignore_dirs = ignore_dirs
    args.no_crawl = no_crawl
    args.psalm_stubs = psalm_stubs
    args.graphql_cop_headers = graphql_cop_headers
    return args


class TestCmdRepoAdd:
    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_creates_repo_and_returns_json(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test repo creation prints JSON and returns SUCCESS."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service

        repo = _create_mock_repo(name="myapp", repo_id=5)
        mock_service.create.return_value = repo

        args = _create_mock_args(repo_name="myapp", repo_path=repo.path)
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["name"] == "myapp"
        assert output["id"] == 5
        assert output["path"] == repo.path

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_error_on_duplicate_name(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test duplicate name raises INVALID_ARGS."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        mock_service.create.side_effect = DuplicateRepositoryName(
            "Repository 'myapp' already exists"
        )

        args = _create_mock_args(repo_name="myapp", repo_path=tempfile.mkdtemp())
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "already exists" in captured.err

    def test_returns_error_when_missing_repo_name(self, capsys) -> None:
        """Test missing --repo-name returns INVALID_ARGS."""
        args = _create_mock_args(repo_name=None, repo_path=tempfile.mkdtemp())
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    def test_returns_error_when_missing_repo_path(self, capsys) -> None:
        """Test missing --repo-path returns INVALID_ARGS."""
        args = _create_mock_args(repo_name="myapp", repo_path=None)
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    def test_returns_error_when_missing_project(self, capsys) -> None:
        """Test missing --project returns INVALID_ARGS."""
        args = _create_mock_args(
            project=None,
            repo_name="myapp",
            repo_path=tempfile.mkdtemp(),
        )
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_parses_comma_separated_languages(
        self, mock_resolve, mock_service_cls
    ) -> None:
        """Test --languages is parsed into list."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        repo = _create_mock_repo()
        mock_service.create.return_value = repo

        args = _create_mock_args(
            repo_name="myapp",
            repo_path=repo.path,
            languages="php,javascript,python",
        )
        cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        call_args = mock_service.create.call_args
        created_repo = call_args[0][1]
        assert created_repo.services[0].languages == [
            "php",
            "javascript",
            "python",
        ]

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_parses_repo_type(self, mock_resolve, mock_service_cls) -> None:
        """Test --repo-type is parsed into service type."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        repo = _create_mock_repo()
        mock_service.create.return_value = repo

        args = _create_mock_args(
            repo_name="myapp",
            repo_path=repo.path,
            repo_type="api,ui",
        )
        cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        call_args = mock_service.create.call_args
        created_repo = call_args[0][1]
        assert created_repo.services[0].type == ["api", "ui"]

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_parses_psalm_stubs(self, mock_resolve, mock_service_cls) -> None:
        """Test --psalm-stubs is parsed into list."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        repo = _create_mock_repo()
        mock_service.create.return_value = repo

        args = _create_mock_args(
            repo_name="myapp",
            repo_path=repo.path,
            psalm_stubs="slim,eloquent",
        )
        cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        call_args = mock_service.create.call_args
        created_repo = call_args[0][1]
        assert created_repo.psalm_stubs == ["slim", "eloquent"]

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_parses_graphql_cop_headers_json(
        self, mock_resolve, mock_service_cls
    ) -> None:
        """Test --graphql-cop-headers is parsed from JSON."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        repo = _create_mock_repo()
        mock_service.create.return_value = repo

        headers_json = '{"Authorization": "Bearer token123"}'
        args = _create_mock_args(
            repo_name="myapp",
            repo_path=repo.path,
            graphql_cop_headers=headers_json,
        )
        cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        call_args = mock_service.create.call_args
        created_repo = call_args[0][1]
        assert created_repo.graphql_cop_headers == {"Authorization": "Bearer token123"}

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_error_on_invalid_graphql_cop_headers_json(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test invalid JSON in --graphql-cop-headers returns INVALID_ARGS."""
        mock_resolve.return_value = (1, MagicMock())

        args = _create_mock_args(
            repo_name="myapp",
            repo_path=tempfile.mkdtemp(),
            graphql_cop_headers="not valid json",
        )
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "JSON" in captured.err

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_project_not_found_on_bad_project(
        self, mock_resolve, capsys
    ) -> None:
        """Test PROJECT_NOT_FOUND when project resolution fails."""
        from application.cli.project import ProjectResolutionError

        mock_resolve.side_effect = ProjectResolutionError("project not found")

        args = _create_mock_args(
            project="nonexistent",
            repo_name="myapp",
            repo_path=tempfile.mkdtemp(),
        )
        result = cmd_repo_add(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == PROJECT_NOT_FOUND


class TestCmdRepoList:
    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_lists_repos_as_json(self, mock_resolve, mock_service_cls, capsys) -> None:
        """Test repo list prints JSON array."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service

        repos = [
            _create_mock_repo(name="repo1", repo_id=1),
            _create_mock_repo(name="repo2", repo_id=2),
        ]
        mock_service.list_active.return_value = repos

        args = _create_mock_args()
        result = cmd_repo_list(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) == 2
        assert output[0]["name"] == "repo1"
        assert output[1]["name"] == "repo2"

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_empty_array_when_no_repos(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test empty list returns empty JSON array."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        mock_service.list_active.return_value = []

        args = _create_mock_args()
        result = cmd_repo_list(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output == []

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_project_not_found_on_bad_project(
        self, mock_resolve, capsys
    ) -> None:
        """Test PROJECT_NOT_FOUND when project resolution fails."""
        from application.cli.project import ProjectResolutionError

        mock_resolve.side_effect = ProjectResolutionError("project not found")

        args = _create_mock_args(project="nonexistent")
        result = cmd_repo_list(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == PROJECT_NOT_FOUND


class TestCmdRepoDelete:
    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_deletes_repo_by_name(self, mock_resolve, mock_service_cls) -> None:
        """Test repo deletion returns SUCCESS."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service

        repo = _create_mock_repo(name="myapp", repo_id=5)
        mock_service.list_active.return_value = [repo]
        mock_service.delete.return_value = None

        args = _create_mock_args(repo_name="myapp")
        result = cmd_repo_delete(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == SUCCESS
        mock_service.delete.assert_called_once_with(1, 5)

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_error_when_repo_not_found(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test PROJECT_NOT_FOUND when repo not found."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        mock_service.list_active.return_value = []

        args = _create_mock_args(repo_name="nonexistent")
        result = cmd_repo_delete(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == PROJECT_NOT_FOUND
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_returns_error_when_missing_repo_name(self, capsys) -> None:
        """Test missing --repo-name returns INVALID_ARGS."""
        args = _create_mock_args(repo_name=None)
        result = cmd_repo_delete(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    def test_returns_error_when_missing_project(self, capsys) -> None:
        """Test missing --project returns INVALID_ARGS."""
        args = _create_mock_args(project=None, repo_name="myapp")
        result = cmd_repo_delete(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err


class TestCmdRepoEdit:
    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_edits_repo_and_returns_json(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test repo edit updates and returns updated JSON."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service

        original = _create_mock_repo(name="myapp", repo_id=5)
        updated = _create_mock_repo(name="myapp", repo_id=5)
        mock_service.list_active.return_value = [original]
        mock_service.update.return_value = updated

        args = _create_mock_args(repo_name="myapp", repo_path=updated.path)
        result = cmd_repo_edit(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == SUCCESS
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["name"] == "myapp"
        assert output["id"] == 5

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_returns_error_when_repo_not_found(
        self, mock_resolve, mock_service_cls, capsys
    ) -> None:
        """Test PROJECT_NOT_FOUND when repo not found."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service
        mock_service.list_active.return_value = []

        args = _create_mock_args(repo_name="nonexistent")
        result = cmd_repo_edit(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == PROJECT_NOT_FOUND
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_returns_error_when_missing_repo_name(self, capsys) -> None:
        """Test missing --repo-name returns INVALID_ARGS."""
        args = _create_mock_args(repo_name=None)
        result = cmd_repo_edit(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    def test_returns_error_when_missing_project(self, capsys) -> None:
        """Test missing --project returns INVALID_ARGS."""
        args = _create_mock_args(project=None, repo_name="myapp")
        result = cmd_repo_edit(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        assert result == INVALID_ARGS
        captured = capsys.readouterr()
        assert "required" in captured.err

    @patch("application.cli.commands.repo.ProjectRepositoriesService")
    @patch("application.cli.commands.repo.resolve_project")
    def test_parses_service_level_updates(self, mock_resolve, mock_service_cls) -> None:
        """Test service-level fields are parsed in edit."""
        mock_resolve.return_value = (1, MagicMock())
        mock_service = MagicMock()
        mock_service_cls.build.return_value = mock_service

        original = _create_mock_repo(name="myapp", repo_id=5)
        updated = _create_mock_repo(name="myapp", repo_id=5)
        mock_service.list_active.return_value = [original]
        mock_service.update.return_value = updated

        args = _create_mock_args(
            repo_name="myapp",
            languages="python,go",
        )
        cmd_repo_edit(
            args,
            MagicMock(),
            MagicMock(),
            Path("/base"),
        )

        call_args = mock_service.update.call_args
        patch_dict = call_args[0][2]
        assert "services" in patch_dict
        assert patch_dict["services"][0]["languages"] == ["python", "go"]
