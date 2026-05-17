"""Unit tests for DefectDojo export adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from domain.findings.entry import Finding
from infrastructure.export.defectdojo.adapter import (
    DefectDojoExportAdapter,
)

_CLIENT_PATH = "infrastructure.export.defectdojo.adapter.DefectDojoClient"


def _config_mock(**overrides: object) -> MagicMock:
    m = MagicMock()
    m.url = overrides.get("url", "http://defectdojo.example.com")
    m.api_token = overrides.get("api_token", "token123")
    m.verify_ssl = overrides.get("verify_ssl", True)
    m.product_type = overrides.get("product_type", "Tally Scan")
    m.engagement_type = overrides.get("engagement_type", "Test Engagement")
    m.auto_create_context = overrides.get("auto_create_context", True)
    m.scan_type = overrides.get("scan_type", "Generic Findings Import")
    return m


def _mock_url_finding(
    repo_id: int = 1,
    protocol: str = "http",
    host: str = "127.0.0.1",
    port: int = 4280,
    path: str = "/search.php",
) -> MagicMock:
    uf = MagicMock()
    uf.repo_id = repo_id
    uf.protocol = protocol
    uf.host = host
    uf.port = port
    uf.path = path
    return uf


def _make_finding(**overrides: object) -> Finding:
    defaults: dict = {
        "id": 1,
        "fingerprint": "fp1",
        "run_id": 1,
        "tool": "test",
        "domain": "code",
        "segment": "sast",
        "severity": "high",
        "confidence": None,
        "description": "Test",
        "file": "test.py",
        "rule_id": "rule1",
        "cwe": [],
        "meta": {},
        "first_seen": "2024-01-15T10:00:00",
        "last_seen": "2024-01-15T10:00:00",
        "seen_count": 1,
        "status": "active",
        "repo_id": 1,
    }
    defaults.update(overrides)
    return Finding(**defaults)


@patch(_CLIENT_PATH)
class TestDefectDojoExportAdapter:
    def test_export_success(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            200,
            {"engagement_id": 1, "findings_count": 2},
        )

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        result = adapter.export_findings([_make_finding()])

        assert result.success is True
        assert result.findings_exported == 1
        assert result.findings_failed == 0

    def test_export_empty_findings(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        result = adapter.export_findings([])

        assert result.success is True
        assert result.findings_exported == 0
        assert result.findings_failed == 0
        client.reimport_scan.assert_not_called()

    def test_export_connection_error(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.side_effect = RuntimeError("Network error")

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert len(result.errors) > 0
        assert "connection error" in result.errors[0]

    def test_export_auth_failure(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            401,
            {"error": "Unauthorized"},
        )

        adapter = DefectDojoExportAdapter(
            config=_config_mock(api_token="invalid_token"),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert "Authentication failed" in result.errors[0]

    def test_export_forbidden_status(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            403,
            {"error": "Forbidden"},
        )

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert "Authentication failed" in result.errors[0]

    def test_export_bad_request(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            400,
            {"error": "Invalid request format"},
        )

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        result = adapter.export_findings([_make_finding()])

        assert result.success is False
        assert result.findings_exported == 0
        assert result.findings_failed == 1
        assert len(result.errors) > 0
        assert "400" in result.errors[0]

    def test_test_connection_success(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.test_connection.return_value = True

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )

        assert adapter.test_connection() is True
        client.test_connection.assert_called_once()

    def test_test_connection_failure(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.test_connection.return_value = False

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )

        assert adapter.test_connection() is False
        client.test_connection.assert_called_once()

    def test_custom_scan_type_passed_to_client(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(scan_type="Tally"),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        adapter.export_findings([_make_finding()])

        call_kwargs = client.reimport_scan.call_args
        assert call_kwargs.kwargs["scan_type"] == "Tally"
        assert call_kwargs.kwargs["test_title"] == "test"

    def test_export_partial_mapping_failure(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (
            200,
            {"status": "success"},
        )

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        good = _make_finding(id=1, fingerprint="fp1")
        bad = _make_finding(
            id=2,
            fingerprint="fp2",
            severity=None,
            description=None,
            meta={"bad_meta": "bad_value"},
        )
        result = adapter.export_findings([good, bad])

        assert result.success is True
        assert result.findings_exported >= 1
        assert result.findings_failed >= 0

    def test_multi_tool_creates_separate_reimports(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", tool="semgrep"),
            _make_finding(id=2, fingerprint="fp2", tool="semgrep"),
            _make_finding(id=3, fingerprint="fp3", tool="gitleaks"),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        assert result.findings_exported == 3
        assert client.reimport_scan.call_count == 2

        titles = {c.kwargs["test_title"] for c in client.reimport_scan.call_args_list}
        assert titles == {"semgrep", "gitleaks"}

    def test_partial_tool_failure_reports_errors(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value

        def side_effect(**kwargs: object) -> tuple[int, dict]:
            if kwargs.get("test_title") == "semgrep":
                return (200, {})
            return (400, {"error": "bad request"})

        client.reimport_scan.side_effect = side_effect

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", tool="semgrep"),
            _make_finding(id=2, fingerprint="fp2", tool="gitleaks"),
        ]
        result = adapter.export_findings(findings)

        assert result.success is False
        assert result.findings_exported == 1
        assert result.findings_failed == 1
        assert any("gitleaks" in e for e in result.errors)

    def test_auth_failure_aborts_all_tools(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (401, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", tool="semgrep"),
            _make_finding(id=2, fingerprint="fp2", tool="gitleaks"),
        ]
        result = adapter.export_findings(findings)

        assert result.success is False
        assert "Authentication failed" in result.errors[0]
        assert client.reimport_scan.call_count == 1

    def test_multi_repo_creates_separate_products(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "repo-a", 2: "repo-b"},
            project_name="proj",
            engagement_type="Test Engagement",
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", tool="semgrep", repo_id=1),
            _make_finding(id=2, fingerprint="fp2", tool="semgrep", repo_id=2),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        assert result.findings_exported == 2
        assert client.reimport_scan.call_count == 2

        products = {
            c.kwargs["product_name"] for c in client.reimport_scan.call_args_list
        }
        assert products == {"proj / repo-a", "proj / repo-b"}

    def test_null_repo_id_uses_unassociated(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "repo-a"},
            project_name="proj",
            engagement_type="Test Engagement",
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", repo_id=None),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        call_kwargs = client.reimport_scan.call_args.kwargs
        assert call_kwargs["product_name"] == "proj / Unassociated"

    def test_engagement_type_passed_to_client(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="CI/CD",
        )
        adapter.export_findings([_make_finding()])

        call_kwargs = client.reimport_scan.call_args.kwargs
        assert call_kwargs["engagement_name"] == "CI/CD"

    def test_product_type_passed_to_client(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(product_type="Custom Type"),
            repo_names={1: "test-repo"},
            project_name="test-project",
            engagement_type="Test Engagement",
        )
        adapter.export_findings([_make_finding()])

        call_kwargs = client.reimport_scan.call_args.kwargs
        assert call_kwargs["product_type_name"] == "Custom Type"

    def test_null_repo_id_resolved_via_run_mapping(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "repo-a"},
            project_name="proj",
            engagement_type="Test Engagement",
            run_to_repo_id={1: 1},
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", repo_id=None, run_id=1),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        call_kwargs = client.reimport_scan.call_args.kwargs
        assert call_kwargs["product_name"] == "proj / repo-a"

    def test_empty_tool_runs_create_tests(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "repo-a"},
            project_name="proj",
            engagement_type="Test Engagement",
            all_tool_runs={(1, "semgrep"), (1, "gitleaks")},
        )
        findings = [
            _make_finding(id=1, fingerprint="fp1", tool="semgrep", repo_id=1),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        assert result.findings_exported == 1
        assert client.reimport_scan.call_count == 2

        titles = {c.kwargs["test_title"] for c in client.reimport_scan.call_args_list}
        assert titles == {"semgrep", "gitleaks"}

    def test_empty_tool_runs_multi_repo(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (200, {})

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "repo-a", 2: "repo-b"},
            project_name="proj",
            engagement_type="Test Engagement",
            all_tool_runs={
                (1, "semgrep"),
                (1, "gitleaks"),
                (2, "semgrep"),
                (2, "gitleaks"),
            },
        )
        findings = [
            _make_finding(
                id=1,
                fingerprint="fp1",
                tool="semgrep",
                repo_id=1,
            ),
        ]
        result = adapter.export_findings(findings)

        assert result.success is True
        assert result.findings_exported == 1
        assert client.reimport_scan.call_count == 4

        calls = client.reimport_scan.call_args_list
        products = {c.kwargs["product_name"] for c in calls}
        assert products == {"proj / repo-a", "proj / repo-b"}

    def test_export_endpoints_creates_dd_endpoints(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.get_product_id.return_value = 42

        url_finding_repo = MagicMock()
        url_finding_repo.list_for_repo.return_value = [
            _mock_url_finding(
                repo_id=1,
                protocol="http",
                host="127.0.0.1",
                port=4280,
                path="/search.php",
            )
        ]

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-proj",
            engagement_type="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_findings([])

        client.create_endpoint.assert_called_once_with(
            42, "http", "127.0.0.1", 4280, "/search.php"
        )

    def test_export_endpoints_filters_external_hosts(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.get_product_id.return_value = 42

        url_finding_repo = MagicMock()
        url_finding_repo.list_for_repo.return_value = [
            _mock_url_finding(
                repo_id=1,
                protocol="http",
                host="external.com",
                port=80,
                path="/search.php",
            )
        ]

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-proj",
            engagement_type="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_findings([])

        client.create_endpoint.assert_not_called()

    def test_export_endpoints_filters_static_assets(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.get_product_id.return_value = 42

        url_finding_repo = MagicMock()
        url_finding_repo.list_for_repo.return_value = [
            _mock_url_finding(
                repo_id=1,
                protocol="http",
                host="127.0.0.1",
                port=4280,
                path="/bundle.js",
            )
        ]

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-proj",
            engagement_type="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_findings([])

        client.create_endpoint.assert_not_called()

    def test_export_endpoints_deduplicates(self, mock_client_cls: MagicMock) -> None:
        client = mock_client_cls.return_value
        client.get_product_id.return_value = 42

        url_finding_repo = MagicMock()
        url_finding_repo.list_for_repo.return_value = [
            _mock_url_finding(
                repo_id=1,
                protocol="http",
                host="127.0.0.1",
                port=4280,
                path="/search.php",
            ),
            _mock_url_finding(
                repo_id=1,
                protocol="http",
                host="127.0.0.1",
                port=4280,
                path="/search.php",
            ),
        ]

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-proj",
            engagement_type="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_findings([])

        assert client.create_endpoint.call_count == 1

    def test_export_endpoints_skipped_when_no_repo(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-proj",
            engagement_type="Test Engagement",
            url_finding_repo=None,
            repo_base_urls=None,
        )
        adapter.export_findings([])

        client.create_endpoint.assert_not_called()
