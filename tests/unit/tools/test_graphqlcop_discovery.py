"""Unit tests for graphqlcop endpoint discovery."""

from unittest.mock import MagicMock

from infrastructure.tools.wrappers.local.graphql_cop import (
    _DEFAULT_GQL_PATHS,
    GraphqlCopLocalTool,
)


class TestGraphqlCopLocalDiscovery:
    """Local wrapper probes all default paths in fallback."""

    def test_fallback_uses_all_default_paths(self):
        tool = GraphqlCopLocalTool()
        repo = MagicMock()
        repo.id = None

        service = MagicMock()
        service.base_urls = ["https://example.com"]
        service.graphql_paths = None

        url_repo = MagicMock()

        urls = tool._discover_gql_endpoints(repo, service, url_repo)

        assert len(urls) == len(_DEFAULT_GQL_PATHS)
        for path in _DEFAULT_GQL_PATHS:
            expected = f"https://example.com{path}"
            assert expected in urls

    def test_explicit_paths_override_defaults(self):
        tool = GraphqlCopLocalTool()
        repo = MagicMock()
        repo.id = None

        service = MagicMock()
        service.base_urls = ["https://example.com"]
        service.graphql_paths = ["/custom/gql"]

        url_repo = MagicMock()

        urls = tool._discover_gql_endpoints(repo, service, url_repo)

        assert urls == {"https://example.com/custom/gql"}


class TestGraphqlCopDockerDiscovery:
    """Docker wrapper probes all default paths."""

    def test_probes_all_default_paths(self):
        from domain.tools.execution_config import ToolExecutionConfig
        from domain.tools.interface import ExecutionContext
        from infrastructure.tools.wrappers.docker.graphql_cop import (
            GraphqlCopDockerTool,
        )

        config = MagicMock()
        config.container.name = "test-container"
        config.container.tool_path = "/usr/bin/graphql-cop"

        tool = GraphqlCopDockerTool(config)

        repo = MagicMock()
        repo.name = "test-repo"
        repo.auth = None
        repo.graphql_cop_headers = None

        service = MagicMock()
        service.base_urls = ["https://example.com"]
        service.graphql_paths = None

        ctx = ExecutionContext(
            project_name="test",
            base_path="/tmp/test",
            repo=repo,
            service=service,
            tool_config=ToolExecutionConfig(
                noir_provider=None,
            ),
            registry=MagicMock(),
            is_docker=True,
        )

        passes = tool.build_execution_passes(ctx)
        assert len(passes) == len(_DEFAULT_GQL_PATHS)

        target_urls = {p.kwargs["target_url"] for p in passes}
        for path in _DEFAULT_GQL_PATHS:
            expected = f"https://example.com{path}"
            assert expected in target_urls
