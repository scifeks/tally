"""Contract tests: verify ZAP can legitimately consume Noir OAS3 output.

These tests verify the handoff contract between Noir and ZAP:

1. A representative Noir OAS3 document is valid OAS3 (openapi 3.x).
2. ZAP's ``build_command`` receives the correct ``-openapifile`` / ``-openapitargeturl``
   argv when an OAS3 file is provided.
3. The existing ZAP ``-quickurl`` mode is unbroken when no OAS3 file is provided.
4. No endpoints are silently dropped between the parser and ZAP: the parser
   extracts exactly the paths that are in the document.
5. Edge cases: empty path set, path parameters, multiple methods per path.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.parsers.noir_parser import parse_noir_json
from infrastructure.tools.wrappers.local.zap import ZAPLocalTool, _find_noir_oas3

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zap(zap_path: str = "zap.sh") -> ZAPLocalTool:
    cfg = MagicMock()
    cfg.path = zap_path
    return ZAPLocalTool(config=cfg)


def _make_repo(base_urls: list[str] | None = None) -> Repository:
    return Repository.model_construct(
        name="dvna",
        type=["api"],
        path="/repo",
        docker_path="",
        container_name="",
        languages=["javascript/typescript"],
        base_urls=base_urls or ["http://localhost:9090"],
        test_dirs=[],
        ignore_dirs=[],
    )


def _make_context(repo: Repository, base_path: str) -> ExecutionContext:
    registry = MagicMock()
    registry.get_repo_path.return_value = repo.path or "/repo"
    return ExecutionContext(
        project_name="DVPA",
        base_path=base_path,
        repo=repo,
        config_manager=MagicMock(),
        registry=registry,
        is_docker=False,
    )


# ---------------------------------------------------------------------------
# OAS3 schema validity
# ---------------------------------------------------------------------------


class TestOas3SchemaValidity:
    """The fixture document must be a well-formed OAS3 document."""

    def test_fixture_is_valid_oas3(self) -> None:
        raw = json.loads((_FIXTURES / "noir_oas3.json").read_text())
        assert raw.get("openapi", "").startswith("3.")
        assert isinstance(raw.get("paths"), dict)
        assert len(raw["paths"]) > 0

    def test_fixture_parses_without_error(self) -> None:
        result = parse_noir_json(_FIXTURES / "noir_oas3.json")
        assert "error" not in result
        assert result["summary"]["total_endpoints"] > 0

    def test_endpoint_count_matches_path_method_product(self) -> None:
        """total_endpoints must equal sum of methods across all paths."""
        raw = json.loads((_FIXTURES / "noir_oas3.json").read_text())
        _HTTP = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
        expected = sum(
            len([m for m in pm.keys() if m.lower() in _HTTP])
            for pm in raw["paths"].values()
            if isinstance(pm, dict)
        )
        result = parse_noir_json(_FIXTURES / "noir_oas3.json")
        assert result["summary"]["total_endpoints"] == expected


# ---------------------------------------------------------------------------
# ZAP build_command — OpenAPI mode
# ---------------------------------------------------------------------------


class TestZapBuildCommandOpenApiMode:
    def test_openapi_file_activates_openapifile_flag(self, tmp_path: Path) -> None:
        oas3 = str(tmp_path / "spec.json")
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target",
            output_file=str(tmp_path / "report.json"),
            openapi_file=oas3,
        )
        assert "-openapifile" in cmd
        assert oas3 in cmd

    def test_openapi_mode_uses_openapitargeturl(self, tmp_path: Path) -> None:
        oas3 = str(tmp_path / "spec.json")
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target:9090",
            output_file=str(tmp_path / "report.json"),
            openapi_file=oas3,
        )
        assert "-openapitargeturl" in cmd
        assert "http://target:9090" in cmd

    def test_openapi_mode_also_contains_quickurl(self, tmp_path: Path) -> None:
        """OpenAPI mode still uses -quickurl to trigger the spider+active scan.

        Without -quickurl, ZAP imports the spec but does not run the scan and
        writes no report.  -quickurl and -openapifile are complementary.
        """
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target",
            output_file=str(tmp_path / "report.json"),
            openapi_file=str(tmp_path / "spec.json"),
        )
        assert "-quickurl" in cmd

    def test_openapi_file_arg_immediately_follows_openapifile_flag(
        self, tmp_path: Path
    ) -> None:
        oas3 = str(tmp_path / "spec.json")
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target",
            output_file=str(tmp_path / "report.json"),
            openapi_file=oas3,
        )
        idx = cmd.index("-openapifile")
        assert cmd[idx + 1] == oas3

    def test_base_url_arg_immediately_follows_openapitargeturl_flag(
        self, tmp_path: Path
    ) -> None:
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target:9090",
            output_file=str(tmp_path / "report.json"),
            openapi_file=str(tmp_path / "spec.json"),
        )
        idx = cmd.index("-openapitargeturl")
        assert cmd[idx + 1] == "http://target:9090"


# ---------------------------------------------------------------------------
# ZAP build_command — quick-scan fallback
# ---------------------------------------------------------------------------


class TestZapBuildCommandQuickScanFallback:
    def test_no_openapi_file_uses_quickurl(self, tmp_path: Path) -> None:
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target",
            output_file=str(tmp_path / "report.json"),
        )
        assert "-quickurl" in cmd
        assert "-openapifile" not in cmd

    def test_none_openapi_file_uses_quickurl(self, tmp_path: Path) -> None:
        zap = _make_zap()
        cmd = zap.build_command(
            base_url="http://target",
            output_file=str(tmp_path / "report.json"),
            openapi_file=None,
        )
        assert "-quickurl" in cmd

    def test_existing_quickout_flag_present_in_both_modes(self, tmp_path: Path) -> None:
        zap = _make_zap()
        report = str(tmp_path / "report.json")
        quick_cmd = zap.build_command(base_url="http://t", output_file=report)
        oas_cmd = zap.build_command(
            base_url="http://t",
            output_file=report,
            openapi_file=str(tmp_path / "spec.json"),
        )
        assert "-quickout" in quick_cmd
        assert "-quickout" in oas_cmd


# ---------------------------------------------------------------------------
# Endpoint integrity: parser ↔ ZAP handoff
# ---------------------------------------------------------------------------


class TestEndpointHandoffIntegrity:
    """No endpoints must be dropped or mangled between Noir parser and ZAP."""

    def test_all_fixture_paths_survive_handoff(self) -> None:
        """Paths in the OAS3 doc match what the parser returns as endpoint paths."""
        raw = json.loads((_FIXTURES / "noir_oas3.json").read_text())
        expected_paths = set(raw["paths"].keys())

        result = parse_noir_json(_FIXTURES / "noir_oas3.json")
        parsed_paths = {ep["path"] for ep in result["endpoints"]}
        assert parsed_paths == expected_paths

    def test_all_fixture_methods_survive_handoff(self) -> None:
        """Every path+method pair in the OAS3 doc appears in parser output."""
        raw = json.loads((_FIXTURES / "noir_oas3.json").read_text())
        _HTTP = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}
        expected_pairs = {
            (path, method.upper())
            for path, pm in raw["paths"].items()
            if isinstance(pm, dict)
            for method in pm.keys()
            if method.lower() in _HTTP
        }
        result = parse_noir_json(_FIXTURES / "noir_oas3.json")
        parsed_pairs = {(ep["path"], ep["method"]) for ep in result["endpoints"]}
        assert parsed_pairs == expected_pairs

    def test_path_params_not_lost_in_handoff(self) -> None:
        result = parse_noir_json(_FIXTURES / "noir_oas3.json")
        vuln_eps = [
            ep
            for ep in result["endpoints"]
            if ep["path"] == "/learn/vulnerability/{vuln}"
        ]
        assert len(vuln_eps) == 1
        assert vuln_eps[0]["path_params"][0]["name"] == "vuln"

    def test_empty_oas3_produces_no_endpoints(self) -> None:
        from infrastructure.tools.parsers.noir_parser import parse_noir_json_string

        empty_doc = json.dumps({"openapi": "3.0.3", "info": {}, "paths": {}})
        result = parse_noir_json_string(empty_doc)
        assert result["endpoints"] == []
        assert result["summary"]["total_endpoints"] == 0


# ---------------------------------------------------------------------------
# _find_noir_oas3 — discovery helper
# ---------------------------------------------------------------------------


class TestFindNoirOas3:
    def test_returns_none_when_dir_missing(self, tmp_path: Path) -> None:
        result = _find_noir_oas3(str(tmp_path), "MYPROJ", "dvna")
        assert result is None

    def test_returns_none_when_no_matching_files(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "MYPROJ" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        result = _find_noir_oas3(str(tmp_path), "MYPROJ", "dvna")
        assert result is None

    def test_returns_path_when_oas3_file_exists(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "MYPROJ" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = noir_dir / "dvna_20260101T120000_oas3.json"
        oas3.write_text("{}", encoding="utf-8")
        result = _find_noir_oas3(str(tmp_path), "MYPROJ", "dvna")
        assert result == str(oas3)

    def test_returns_latest_when_multiple_files(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "MYPROJ" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        f1 = noir_dir / "dvna_20260101T120000_oas3.json"
        f2 = noir_dir / "dvna_20260102T120000_oas3.json"
        f1.write_text("{}", encoding="utf-8")
        f2.write_text("{}", encoding="utf-8")
        result = _find_noir_oas3(str(tmp_path), "MYPROJ", "dvna")
        # lexicographically last = most recent timestamp
        assert result == str(f2)

    def test_does_not_match_different_repo(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "MYPROJ" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        (noir_dir / "other_repo_20260101T120000_oas3.json").write_text("{}")
        result = _find_noir_oas3(str(tmp_path), "MYPROJ", "dvna")
        assert result is None


# ---------------------------------------------------------------------------
# build_execution_passes with Noir OAS3 discovery
# ---------------------------------------------------------------------------


class TestZapBuildExecutionPassesWithNoir:
    def test_no_noir_output_produces_no_openapi_file_kwarg(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        zap = _make_zap()
        passes = zap.build_execution_passes(ctx)
        assert "openapi_file" not in passes[0].kwargs

    def test_noir_oas3_present_adds_openapi_file_kwarg(self, tmp_path: Path) -> None:
        repo = _make_repo()
        noir_dir = tmp_path / "projects" / "DVPA" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = noir_dir / "dvna_20260101T120000_oas3.json"
        oas3.write_text("{}", encoding="utf-8")

        ctx = _make_context(repo, str(tmp_path))
        zap = _make_zap()
        passes = zap.build_execution_passes(ctx)
        assert passes[0].kwargs.get("openapi_file") == str(oas3)

    def test_base_url_always_present(self, tmp_path: Path) -> None:
        repo = _make_repo(["http://localhost:9090"])
        ctx = _make_context(repo, str(tmp_path))
        zap = _make_zap()
        passes = zap.build_execution_passes(ctx)
        assert passes[0].kwargs["base_url"] == "http://localhost:9090"
