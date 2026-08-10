"""Unit tests for apidocs wrapper and parser."""

import pytest
import yaml

from infrastructure.tools.parsers.apidocs import (
    _extract_endpoints,
    parse_apidocs_output,
)
from infrastructure.tools.wrappers.local.apidocs import ApidocsLocalTool


class TestApidocsLocalToolBuildCommand:
    """Test ApidocsLocalTool.build_command() stage dispatch."""

    def test_recon_stage_command(self):
        """Test recon stage builds correct command."""
        tool = ApidocsLocalTool()
        cmd = tool.build_command(
            stage="recon",
            repo_path="/tmp/repo",
            output_file="/tmp/out.json",
        )
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--agent" in cmd
        assert "apidocs-recon" in cmd

    def test_discovery_stage_command(self):
        """Test discovery stage builds correct command."""
        tool = ApidocsLocalTool()
        cmd = tool.build_command(
            stage="discovery",
            repo_path="/tmp/repo",
            output_file="/tmp/out.json",
        )
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--agent" in cmd
        assert "apidocs-discovery" in cmd

    def test_enrich_stage_command(self):
        """Test enrich stage builds correct command."""
        tool = ApidocsLocalTool()
        repo_path = "/tmp/test_repo"
        cmd = tool.build_command(
            stage="enrich",
            repo_path=repo_path,
            output_file="/tmp/out.json",
        )
        assert cmd[0] == "bash"
        assert "--repo" in cmd
        idx = cmd.index("--repo")
        assert cmd[idx + 1] == repo_path

    def test_assemble_stage_command(self):
        """Test assemble stage builds correct command."""
        tool = ApidocsLocalTool()
        cmd = tool.build_command(
            stage="assemble",
            repo_path="/tmp/repo",
            output_file="/tmp/out.json",
        )
        assert cmd[0] == "claude"
        assert "-p" in cmd
        # Check that the prompt text contains the assemble instruction
        prompt_text = " ".join(cmd)
        assert "apidocs-assemble" in prompt_text

    def test_unknown_stage_raises_valueerror(self):
        """Test unknown stage raises ValueError."""
        tool = ApidocsLocalTool()
        with pytest.raises(ValueError, match="Unknown apidocs stage"):
            tool.build_command(
                stage="invalid_stage",
                repo_path="/tmp/repo",
                output_file="/tmp/out.json",
            )


class TestBaseApidocsToolProperties:
    """Test BaseApidocsTool property values."""

    def test_name_property(self):
        """Test name property returns 'apidocs'."""
        tool = ApidocsLocalTool()
        assert tool.name == "apidocs"

    def test_scan_segment_property(self):
        """Test scan_segment property returns 'web'."""
        tool = ApidocsLocalTool()
        assert tool.scan_segment == "web"

    def test_skip_property(self):
        """Test skip property returns True."""
        tool = ApidocsLocalTool()
        assert tool.skip is True

    def test_is_discovery_tool_property(self):
        """Test is_discovery_tool property returns True."""
        tool = ApidocsLocalTool()
        assert tool.is_discovery_tool is True

    def test_should_visualize_property(self):
        """Test should_visualize property returns False."""
        tool = ApidocsLocalTool()
        assert tool.should_visualize is False

    def test_always_run_property(self):
        """Test always_run property returns True."""
        tool = ApidocsLocalTool()
        assert tool.always_run is True


class TestParseApidocsOutput:
    """Test parse_apidocs_output() function."""

    def test_parse_yaml_spec_creates_json_output(self, tmp_path):
        """Test reading YAML spec converts to JSON and writes output."""
        # Create apidocs/openapi directory with a minimal OAS3 YAML file
        openapi_dir = tmp_path / "apidocs" / "openapi"
        openapi_dir.mkdir(parents=True)

        oas3_doc = {
            "openapi": "3.0.0",
            "info": {
                "title": "Test API",
                "version": "1.0.0",
            },
            "paths": {
                "/users": {
                    "get": {
                        "summary": "List users",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {"type": "integer"},
                            }
                        ],
                    },
                    "post": {
                        "summary": "Create user",
                        "requestBody": {
                            "content": {
                                "application/json": {"schema": {"type": "object"}}
                            },
                        },
                    },
                },
            },
        }

        spec_file = openapi_dir / "api.yaml"
        spec_file.write_text(yaml.dump(oas3_doc), encoding="utf-8")

        output_file = tmp_path / "output" / "spec.json"
        files = {}

        result = parse_apidocs_output(
            repo_path=str(tmp_path),
            output_file=str(output_file),
            files=files,
        )

        # Verify output file was written
        assert output_file.exists()
        assert files["oas3"] == output_file

        # Verify result contains endpoints
        assert "endpoints" in result
        assert len(result["endpoints"]) == 2  # GET and POST

    def test_missing_openapi_dir_returns_error(self, tmp_path):
        """Test missing openapi dir returns error dict."""
        files = {}
        result = parse_apidocs_output(
            repo_path=str(tmp_path),
            output_file=str(tmp_path / "out.json"),
            files=files,
        )

        assert "error" in result
        assert "apidocs/openapi" in result["error"]
        assert result["endpoints"] == []

    def test_empty_openapi_dir_returns_error(self, tmp_path):
        """Test empty openapi dir returns error dict."""
        openapi_dir = tmp_path / "apidocs" / "openapi"
        openapi_dir.mkdir(parents=True)

        files = {}
        result = parse_apidocs_output(
            repo_path=str(tmp_path),
            output_file=str(tmp_path / "out.json"),
            files=files,
        )

        assert "error" in result
        assert "no OAS3 files" in result["error"]
        assert result["endpoints"] == []


class TestExtractEndpoints:
    """Test _extract_endpoints() helper function."""

    def test_extracts_multiple_http_methods(self):
        """Test extracting multiple HTTP methods from paths."""
        doc = {
            "paths": {
                "/users": {
                    "get": {
                        "summary": "List users",
                        "parameters": [
                            {
                                "name": "id",
                                "in": "query",
                                "schema": {"type": "string"},
                            }
                        ],
                    },
                    "post": {
                        "summary": "Create user",
                        "requestBody": {"content": {"application/json": {}}},
                    },
                },
                "/users/{id}": {
                    "get": {
                        "summary": "Get user",
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "schema": {"type": "string"},
                            }
                        ],
                    },
                    "put": {
                        "summary": "Update user",
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "schema": {"type": "string"},
                            }
                        ],
                    },
                    "delete": {
                        "summary": "Delete user",
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "schema": {"type": "string"},
                            }
                        ],
                    },
                },
            }
        }

        endpoints = _extract_endpoints(doc)

        # Should have 5 endpoints total
        assert len(endpoints) == 5

        # Verify methods are in uppercase
        methods = {ep["method"] for ep in endpoints}
        assert methods == {"GET", "POST", "PUT", "DELETE"}

        # Verify paths are preserved
        paths = {ep["path"] for ep in endpoints}
        assert "/users" in paths
        assert "/users/{id}" in paths

    def test_ignores_non_http_keys(self):
        """Test ignoring non-HTTP method keys like summary and parameters."""
        doc = {
            "paths": {
                "/api/items": {
                    "summary": "Items endpoint",
                    "description": "Manages items",
                    "get": {
                        "summary": "List items",
                    },
                    "post": {
                        "summary": "Create item",
                    },
                    "x-custom": {"some": "value"},
                    "parameters": [{"name": "filter", "in": "query"}],
                }
            }
        }

        endpoints = _extract_endpoints(doc)

        # Should only have 2 endpoints (GET and POST)
        assert len(endpoints) == 2

        methods = {ep["method"] for ep in endpoints}
        assert methods == {"GET", "POST"}

    def test_handles_lowercase_http_methods(self):
        """Test that lowercase HTTP method names are handled."""
        doc = {
            "paths": {
                "/data": {
                    "get": {"summary": "Get data"},
                    "options": {"summary": "Options"},
                    "head": {"summary": "Head"},
                    "patch": {"summary": "Patch"},
                }
            }
        }

        endpoints = _extract_endpoints(doc)

        # Should have 4 endpoints
        assert len(endpoints) == 4

        # All methods should be uppercase in output
        for ep in endpoints:
            assert ep["method"] in {"GET", "OPTIONS", "HEAD", "PATCH"}
