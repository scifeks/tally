"""Unit tests for LlmScan scan type strategy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.llm_scan import LlmScan
from domain.tools.scan_types.models import ScanSummary


class TestLlmScanExecute:
    """Test LlmScan.execute() behavior."""

    @pytest.fixture
    def mock_resources(self) -> MagicMock:
        """Create mock execution resources."""
        resources = MagicMock()
        resources.event_bus = MagicMock()
        resources.display = MagicMock()
        resources.event_sink = MagicMock()
        return resources

    @pytest.fixture
    def mock_config(self) -> MagicMock:
        """Create mock scan type config."""
        config = MagicMock()
        config.run_id = 1
        config.project_id = 100
        config.project_name = "test-project"
        config.base_path = "/app"
        return config

    def test_no_repos_configured(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan returns empty summary when no repos configured."""
        mock_config.repo_repo = None
        scan = LlmScan()

        result = scan.execute(mock_config, mock_resources)

        assert isinstance(result, ScanSummary)
        assert result.total_tools_run == 0
        assert result.total_tools_skipped == 0
        assert result.total_tools_failed == 0
        assert result.findings_ingested == 0
        assert len(result.results) == 0
        mock_resources.display.print_status.assert_called_once()

    def test_empty_active_repos_list(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan returns empty summary when repos list is empty."""
        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = []
        scan = LlmScan()

        result = scan.execute(mock_config, mock_resources)

        assert result.total_tools_run == 0
        assert result.total_tools_skipped == 0
        assert result.findings_ingested == 0

    def test_filters_to_requested_repos(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan filters repos when repo_names is provided."""
        repo1 = MagicMock()
        repo1.name = "repo1"
        repo1.path = "/repos/repo1"

        repo2 = MagicMock()
        repo2.name = "repo2"
        repo2.path = "/repos/repo2"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo1, repo2]

        scan = LlmScan(repo_names=["repo1"])

        with patch(
            "application.tools.scan_types.llm_scan.create_llm_scan_backend"
        ) as mock_factory:
            mock_backend = MagicMock()
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = MagicMock(
                success=False, findings=[], raw_output="", error="test error"
            )
            mock_factory.return_value = (mock_backend, 300)

            with (
                patch("application.tools.scan_types.llm_scan.build_tree") as mock_tree,
                patch(
                    "application.tools.scan_types.llm_scan.build_scan_prompt"
                ) as mock_prompt,
                patch(
                    "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
                ) as mock_dispatch,
            ):
                mock_tree.return_value = "tree"
                mock_prompt.return_value = "prompt"
                mock_dispatch.return_value = 0

                scan.execute(mock_config, mock_resources)

                # Verify factory was called with only repo1
                mock_factory.assert_called_once()
                call_kwargs = mock_factory.call_args[1]
                assert "repo1" in call_kwargs["repo_paths"]
                assert "repo2" not in call_kwargs["repo_paths"]

    def test_successful_scan_single_repo(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan succeeds for a single repo with findings."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        finding = MagicMock()
        finding.file_path = "src/app.py"
        finding.line_number = 42
        finding.description = "SQL injection found"
        finding.severity = "high"
        finding.confidence = "confirmed"
        finding.finding_type = ["vulnerability"]
        finding.segment = "sast"
        finding.reasoning = "Direct string interpolation in SQL query"
        finding.remediation = "Use parameterized queries"
        finding.rule_id = "sql-injection"
        finding.cwe = ["CWE-89"]
        finding.attack_vector = "network"
        finding.code_snippet = "query = f'SELECT * FROM users WHERE id={id}'"

        scan_result = MagicMock()
        scan_result.success = True
        scan_result.findings = [finding]
        scan_result.raw_output = "scan output"

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree") as mock_tree,
            patch(
                "application.tools.scan_types.llm_scan.build_scan_prompt"
            ) as mock_prompt,
            patch(
                "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
            ) as mock_dispatch,
        ):
            mock_backend = MagicMock()
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = scan_result
            mock_factory.return_value = (mock_backend, 300)

            mock_tree.return_value = "tree content"
            mock_prompt.return_value = "prompt content"
            mock_dispatch.return_value = 1

            result = scan.execute(mock_config, mock_resources)

            assert result.total_tools_run == 1
            assert result.total_tools_failed == 0
            assert result.findings_ingested == 1
            assert len(result.results) == 1
            assert result.results[0].success is True
            assert result.results[0].finding_count == 1

            # Verify tree and prompt were built for the repo
            mock_tree.assert_called_once_with(Path("/repos/test-repo"), max_depth=4)
            mock_prompt.assert_called_once()

            # Verify events were emitted
            assert mock_resources.event_sink.emit.call_count >= 4

    def test_scan_failure_increments_failed_count(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan counts failed tools when backend returns success=False."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        scan_result = MagicMock()
        scan_result.success = False
        scan_result.findings = []
        scan_result.raw_output = ""
        scan_result.error = "Backend error"

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree"),
            patch("application.tools.scan_types.llm_scan.build_scan_prompt"),
            patch("application.tools.scan_types.llm_scan.dispatch_and_count_ingested"),
        ):
            mock_backend = MagicMock()
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = scan_result
            mock_factory.return_value = (mock_backend, 300)

            result = scan.execute(mock_config, mock_resources)

            assert result.total_tools_run == 0
            assert result.total_tools_failed == 1
            assert result.findings_ingested == 0

    def test_exception_during_scan_caught_and_counted(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan catches exceptions and counts as failed tool."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree") as mock_tree,
        ):
            mock_backend = MagicMock()
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.side_effect = RuntimeError("Backend crashed")
            mock_factory.return_value = (mock_backend, 300)
            mock_tree.return_value = "tree"

            result = scan.execute(mock_config, mock_resources)

            assert result.total_tools_run == 0
            assert result.total_tools_failed == 1

    def test_claude_backend_sets_tool_name_to_claudecode(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Claude backend sets tool name to claudecode."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        scan_result = MagicMock()
        scan_result.success = True
        scan_result.findings = []
        scan_result.raw_output = ""

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree"),
            patch("application.tools.scan_types.llm_scan.build_scan_prompt"),
            patch(
                "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
            ) as mock_dispatch,
        ):
            mock_backend = MagicMock()
            mock_backend.__class__.__name__ = "ClaudeLlmScanAdapter"
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = scan_result
            mock_factory.return_value = (mock_backend, 300)
            mock_dispatch.return_value = 0

            result = scan.execute(mock_config, mock_resources)

            # Verify tool name is claudecode
            assert result.results[0].tool_name == "claudecode"

    def test_opencode_backend_sets_tool_name_to_opencode(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """OpenCode backend sets tool name to opencode."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        scan_result = MagicMock()
        scan_result.success = True
        scan_result.findings = []
        scan_result.raw_output = ""

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree"),
            patch("application.tools.scan_types.llm_scan.build_scan_prompt"),
            patch(
                "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
            ) as mock_dispatch,
        ):
            mock_backend = MagicMock()
            mock_backend.__class__.__name__ = "OpenCodeLlmScanAdapter"
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = scan_result
            mock_factory.return_value = (mock_backend, 300)
            mock_dispatch.return_value = 0

            result = scan.execute(mock_config, mock_resources)

            # Verify tool name is opencode
            assert result.results[0].tool_name == "opencode"

    def test_multiple_repos_scanned_sequentially(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Scan processes multiple repos and accumulates results."""
        repo1 = MagicMock()
        repo1.name = "repo1"
        repo1.path = "/repos/repo1"

        repo2 = MagicMock()
        repo2.name = "repo2"
        repo2.path = "/repos/repo2"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo1, repo2]

        scan_result1 = MagicMock()
        scan_result1.success = True
        scan_result1.findings = [MagicMock()] * 2
        scan_result1.raw_output = ""

        scan_result2 = MagicMock()
        scan_result2.success = True
        scan_result2.findings = [MagicMock()] * 3
        scan_result2.raw_output = ""

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree"),
            patch("application.tools.scan_types.llm_scan.build_scan_prompt"),
            patch(
                "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
            ) as mock_dispatch,
        ):
            mock_backend = MagicMock()
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.side_effect = [scan_result1, scan_result2]
            mock_factory.return_value = (mock_backend, 300)
            mock_dispatch.return_value = 5

            result = scan.execute(mock_config, mock_resources)

            assert result.total_tools_run == 2
            assert len(result.results) == 2
            assert result.results[0].repo == "repo1"
            assert result.results[0].finding_count == 2
            assert result.results[1].repo == "repo2"
            assert result.results[1].finding_count == 3

    def test_parsed_data_structure_complete(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Parsed data structure includes all finding fields."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        finding = MagicMock()
        finding.file_path = "src/app.py"
        finding.line_number = 42
        finding.description = "SQL injection"
        finding.severity = "high"
        finding.confidence = "confirmed"
        finding.finding_type = ["vulnerability"]
        finding.segment = "sast"
        finding.reasoning = "Direct string interpolation"
        finding.remediation = "Use parameterized queries"
        finding.rule_id = "sql-injection"
        finding.cwe = ["CWE-89"]
        finding.attack_vector = "network"
        finding.code_snippet = "query = f'SELECT * FROM users WHERE id={id}'"

        scan_result = MagicMock()
        scan_result.success = True
        scan_result.findings = [finding]
        scan_result.raw_output = "scan output"

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree"),
            patch("application.tools.scan_types.llm_scan.build_scan_prompt"),
            patch(
                "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
            ) as mock_dispatch,
        ):
            mock_backend = MagicMock()
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = scan_result
            mock_factory.return_value = (mock_backend, 300)
            mock_dispatch.return_value = 1

            result = scan.execute(mock_config, mock_resources)

            parsed_data = result.results[0].parsed_data
            assert parsed_data is not None
            assert "findings" in parsed_data
            assert len(parsed_data["findings"]) == 1

            finding_obj = parsed_data["findings"][0]
            assert finding_obj["file_path"] == "src/app.py"
            assert finding_obj["line_number"] == 42
            assert finding_obj["description"] == "SQL injection"
            assert finding_obj["severity"] == "high"
            assert finding_obj["confidence"] == "confirmed"
            assert finding_obj["finding_type"] == ["vulnerability"]
            assert finding_obj["segment"] == "sast"
            assert finding_obj["reasoning"] == "Direct string interpolation"
            assert finding_obj["remediation"] == "Use parameterized queries"
            assert finding_obj["rule_id"] == "sql-injection"
            assert finding_obj["cwe"] == ["CWE-89"]
            assert finding_obj["attack_vector"] == "network"
            assert finding_obj["code_snippet"] == (
                "query = f'SELECT * FROM users WHERE id={id}'"
            )

    def test_summary_includes_findings_by_tool(
        self, mock_resources: MagicMock, mock_config: MagicMock
    ) -> None:
        """Summary includes findings aggregated by tool."""
        repo = MagicMock()
        repo.name = "test-repo"
        repo.path = "/repos/test-repo"

        mock_config.repo_repo = MagicMock()
        mock_config.repo_repo.list_active.return_value = [repo]

        finding1 = MagicMock()
        finding1.file_path = "src/app.py"
        finding1.line_number = None
        finding1.description = "Issue 1"
        finding1.severity = "high"
        finding1.confidence = "confirmed"
        finding1.finding_type = ["vulnerability"]
        finding1.segment = "sast"
        finding1.reasoning = "Reason 1"
        finding1.remediation = "Fix 1"
        finding1.rule_id = "rule1"
        finding1.cwe = []
        finding1.attack_vector = ""
        finding1.code_snippet = ""

        finding2 = MagicMock()
        finding2.file_path = "src/app.py"
        finding2.line_number = None
        finding2.description = "Issue 2"
        finding2.severity = "medium"
        finding2.confidence = "probable"
        finding2.finding_type = ["vulnerability"]
        finding2.segment = "sast"
        finding2.reasoning = "Reason 2"
        finding2.remediation = "Fix 2"
        finding2.rule_id = "rule2"
        finding2.cwe = []
        finding2.attack_vector = ""
        finding2.code_snippet = ""

        scan_result = MagicMock()
        scan_result.success = True
        scan_result.findings = [finding1, finding2]
        scan_result.raw_output = ""

        scan = LlmScan()

        with (
            patch(
                "application.tools.scan_types.llm_scan.create_llm_scan_backend"
            ) as mock_factory,
            patch("application.tools.scan_types.llm_scan.build_tree"),
            patch("application.tools.scan_types.llm_scan.build_scan_prompt"),
            patch(
                "application.tools.scan_types.llm_scan.dispatch_and_count_ingested"
            ) as mock_dispatch,
        ):
            mock_backend = MagicMock()
            mock_backend.__class__.__name__ = "ClaudeLlmScanAdapter"
            mock_backend.prepare_session.return_value.__enter__ = MagicMock()
            mock_backend.prepare_session.return_value.__exit__ = MagicMock(
                return_value=False
            )
            mock_backend.run_scan.return_value = scan_result
            mock_factory.return_value = (mock_backend, 300)
            mock_dispatch.return_value = 2

            result = scan.execute(mock_config, mock_resources)

            assert "claudecode" in result.findings_by_tool
            assert result.findings_by_tool["claudecode"] == 2
