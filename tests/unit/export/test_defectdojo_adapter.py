"""Unit tests for DefectDojo export adapter."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from application.ports.export import SyncBatch
from domain.findings.entry import Finding
from infrastructure.export.defectdojo.adapter import (
    DefectDojoExportAdapter,
)

_CLIENT_PATH = "infrastructure.export.defectdojo.adapter.DefectDojoClient"
_MAP_PATH = "infrastructure.export.defectdojo.adapter.map_findings"


def _config_mock(**overrides: object) -> MagicMock:
    m = MagicMock()
    m.url = overrides.get("url", "http://defectdojo.example.com")
    m.api_token = overrides.get("api_token", "token123")
    m.verify_ssl = overrides.get("verify_ssl", True)
    m.auto_create_context = overrides.get("auto_create_context", True)
    m.scan_type = overrides.get("scan_type", "Generic Findings Import")
    return m


def _adapter() -> DefectDojoExportAdapter:
    return DefectDojoExportAdapter(
        config=_config_mock(),
        repo_names={1: "repo-a", 2: "repo-b"},
        project_name="proj",
        organization_name="Acme",
        engagement_name="Test Engagement",
    )


def _batch(repo_id: int = 1, tool: str = "semgrep", count: int = 1) -> SyncBatch:
    findings = tuple(
        _make_finding(id=i + 1, tool=tool, repo_id=repo_id) for i in range(count)
    )
    return SyncBatch(repo_id, tool, findings)


def _ok(engagement_id: int) -> tuple[int, dict]:
    return 201, {"engagement_id": engagement_id}


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
    def test_batch_goes_to_the_repo_product_under_the_organization(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = _ok(11)

        result = _adapter().export_batches([_batch(repo_id=2, tool="zap", count=2)])

        kwargs = client.reimport_scan.call_args.kwargs
        assert kwargs["product_type_name"] == "Acme"
        assert kwargs["product_name"] == "proj / repo-b"
        assert kwargs["engagement_name"] == "Test Engagement"
        assert kwargs["test_title"] == "zap"
        assert (result.success, result.findings_exported) == (True, 2)

    def test_empty_batch_is_sent_with_no_findings(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = _ok(11)

        result = _adapter().export_batches([_batch(count=0)])

        assert client.reimport_scan.call_args.kwargs["json_payload"] == (
            b'{"findings": []}'
        )
        assert result.success is True

    def test_batch_that_fails_to_map_entirely_is_not_sent(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value

        with patch(_MAP_PATH, return_value=[]):
            result = _adapter().export_batches([_batch(count=2)])

        client.reimport_scan.assert_not_called()
        assert result.success is False
        assert result.findings_failed == 2

    def test_engagement_type_is_set_once_per_repo(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.side_effect = [_ok(11), _ok(11), _ok(22)]
        client.set_engagement_type.return_value = True

        _adapter().export_batches(
            [_batch(1, "semgrep"), _batch(1, "zap"), _batch(2, "semgrep")]
        )

        assert client.set_engagement_type.call_args_list == [
            call(11, "Interactive"),
            call(22, "Interactive"),
        ]

    def test_engagement_type_waits_for_the_first_successful_send(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.side_effect = [(500, {"detail": "boom"}), _ok(11)]
        client.set_engagement_type.return_value = True

        result = _adapter().export_batches([_batch(1, "semgrep"), _batch(1, "zap")])

        client.set_engagement_type.assert_called_once_with(11, "Interactive")
        assert (result.success, result.findings_exported) == (False, 1)

    def test_failed_type_change_does_not_fail_the_sync(
        self, mock_client_cls: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = _ok(11)
        client.set_engagement_type.return_value = False

        with caplog.at_level(logging.WARNING):
            result = _adapter().export_batches([_batch()])

        assert result.success is True
        assert result.errors == ()
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("Interactive" in w and "proj / repo-a" in w for w in warnings)

    @pytest.mark.parametrize(
        ("outcome", "message"),
        [
            (RuntimeError("Network error"), "connection error"),
            ((401, {"detail": "bad token"}), "Authentication failed"),
            ((403, {"detail": "forbidden"}), "Authentication failed"),
            ((400, {"detail": "bad"}), "DefectDojo returned 400"),
        ],
        ids=["unreachable", "unauthorized", "forbidden", "rejected"],
    )
    def test_failed_send_is_reported(
        self, mock_client_cls: MagicMock, outcome: object, message: str
    ) -> None:
        client = mock_client_cls.return_value
        if isinstance(outcome, Exception):
            client.reimport_scan.side_effect = outcome
        else:
            client.reimport_scan.return_value = outcome

        result = _adapter().export_batches([_batch()])

        assert result.success is False
        assert result.findings_failed == 1
        assert message in result.errors[0]
        client.set_engagement_type.assert_not_called()

    def test_auth_failure_stops_the_remaining_batches(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value
        client.reimport_scan.return_value = (401, {"detail": "bad token"})

        _adapter().export_batches([_batch(1, "semgrep"), _batch(2, "semgrep")])

        assert client.reimport_scan.call_count == 1

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
            organization_name="Acme",
            engagement_name="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_batches([])

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
            organization_name="Acme",
            engagement_name="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_batches([])

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
            organization_name="Acme",
            engagement_name="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_batches([])

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
            organization_name="Acme",
            engagement_name="Test Engagement",
            url_finding_repo=url_finding_repo,
            repo_base_urls={1: ["http://127.0.0.1:4280"]},
        )
        adapter.export_batches([])

        assert client.create_endpoint.call_count == 1

    def test_export_endpoints_skipped_when_no_repo(
        self, mock_client_cls: MagicMock
    ) -> None:
        client = mock_client_cls.return_value

        adapter = DefectDojoExportAdapter(
            config=_config_mock(),
            repo_names={1: "test-repo"},
            project_name="test-proj",
            organization_name="Acme",
            engagement_name="Test Engagement",
            url_finding_repo=None,
            repo_base_urls=None,
        )
        adapter.export_batches([])

        client.create_endpoint.assert_not_called()
