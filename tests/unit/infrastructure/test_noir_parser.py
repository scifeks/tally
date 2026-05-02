"""Unit tests for infrastructure.tools.parsers.noir."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.tools.parsers.noir import (
    parse_noir_json,
    parse_noir_json_string,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ingest"


# parse_noir_json_string: edge cases


class TestParseNoirJsonString:
    def test_empty_string_returns_zero_endpoints(self) -> None:
        result = parse_noir_json_string("")
        assert result["endpoints"] == []
        assert result["summary"]["total_endpoints"] == 0

    def test_whitespace_only_returns_zero_endpoints(self) -> None:
        result = parse_noir_json_string("   ")
        assert result["endpoints"] == []
        assert result["summary"]["total_endpoints"] == 0

    def test_malformed_json_returns_error_key(self) -> None:
        result = parse_noir_json_string("{not valid json}")
        assert "error" in result
        assert result["endpoints"] == []

    def test_non_dict_root_returns_error(self) -> None:
        result = parse_noir_json_string(json.dumps([1, 2, 3]))
        assert "error" in result

    def test_oas2_version_returns_error(self) -> None:
        doc = {"swagger": "2.0", "openapi": "2.0", "paths": {}}
        result = parse_noir_json_string(json.dumps(doc))
        assert "error" in result

    def test_valid_oas3_no_paths_returns_zero(self) -> None:
        doc = {"openapi": "3.0.3", "info": {}, "paths": {}}
        result = parse_noir_json_string(json.dumps(doc))
        assert result["endpoints"] == []
        assert result["summary"]["total_paths"] == 0

    def test_missing_paths_key_returns_zero(self) -> None:
        doc = {"openapi": "3.0.3", "info": {}}
        result = parse_noir_json_string(json.dumps(doc))
        assert result["endpoints"] == []

    def test_paths_not_dict_returns_zero(self) -> None:
        doc = {"openapi": "3.0.3", "info": {}, "paths": "bad"}
        result = parse_noir_json_string(json.dumps(doc))
        assert result["endpoints"] == []


# Endpoint extraction


class TestEndpointExtraction:
    def _doc(self, paths: dict) -> str:
        return json.dumps({"openapi": "3.0.3", "paths": paths})

    def test_single_get_endpoint(self) -> None:
        doc = self._doc({"/login": {"get": {"parameters": [], "responses": {}}}})
        result = parse_noir_json_string(doc)
        assert result["summary"]["total_endpoints"] == 1
        ep = result["endpoints"][0]
        assert ep["path"] == "/login"
        assert ep["method"] == "GET"

    def test_multiple_methods_on_same_path(self) -> None:
        doc = self._doc(
            {
                "/login": {
                    "get": {"parameters": [], "responses": {}},
                    "post": {"parameters": [], "responses": {}},
                }
            }
        )
        result = parse_noir_json_string(doc)
        assert result["summary"]["total_endpoints"] == 2
        methods = {ep["method"] for ep in result["endpoints"]}
        assert methods == {"GET", "POST"}

    def test_path_parameter_extracted(self) -> None:
        doc = self._doc(
            {
                "/vuln/{id}": {
                    "get": {
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {},
                    }
                }
            }
        )
        result = parse_noir_json_string(doc)
        assert result["summary"]["total_endpoints"] == 1
        ep = result["endpoints"][0]
        assert len(ep["path_params"]) == 1
        assert ep["path_params"][0]["name"] == "id"
        assert ep["path_params"][0]["required"] is True
        assert ep["has_params"] is True

    def test_query_parameter_extracted(self) -> None:
        doc = self._doc(
            {
                "/search": {
                    "get": {
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {},
                    }
                }
            }
        )
        result = parse_noir_json_string(doc)
        ep = result["endpoints"][0]
        assert len(ep["query_params"]) == 1
        assert ep["query_params"][0]["name"] == "q"

    def test_request_body_properties_extracted(self) -> None:
        doc = self._doc(
            {
                "/login": {
                    "post": {
                        "parameters": [],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "username": {"type": "string"},
                                            "password": {"type": "string"},
                                        },
                                        "required": ["username"],
                                    }
                                }
                            },
                        },
                        "responses": {},
                    }
                }
            }
        )
        result = parse_noir_json_string(doc)
        ep = result["endpoints"][0]
        assert len(ep["body_params"]) == 2
        names = {p["name"] for p in ep["body_params"]}
        assert names == {"username", "password"}
        req = {p["name"]: p["required"] for p in ep["body_params"]}
        assert req["username"] is True
        assert req["password"] is False

    def test_no_params_has_params_false(self) -> None:
        doc = self._doc({"/noop": {"get": {"parameters": [], "responses": {}}}})
        result = parse_noir_json_string(doc)
        assert result["endpoints"][0]["has_params"] is False

    def test_non_http_method_keys_ignored(self) -> None:
        """Keys like 'summary', 'parameters' at path-item level must be ignored."""
        doc = self._doc(
            {
                "/api": {
                    "summary": "some summary",
                    "get": {"parameters": [], "responses": {}},
                }
            }
        )
        result = parse_noir_json_string(doc)
        assert result["summary"]["total_endpoints"] == 1


# parse_noir_json: file-based path


class TestParseNoirJsonFile:
    def test_fixture_file_loaded(self, tmp_path: Path) -> None:
        fixture = _FIXTURES / "noir_oas3.json"
        result = parse_noir_json(fixture)
        assert "error" not in result
        assert result["summary"]["total_endpoints"] > 0

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        result = parse_noir_json(tmp_path / "nonexistent.json")
        assert "error" in result

    def test_invalid_json_file_returns_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid}", encoding="utf-8")
        result = parse_noir_json(bad)
        assert "error" in result

    def test_empty_file_returns_zero_endpoints(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        result = parse_noir_json(empty)
        assert result["endpoints"] == []


# Fixture-based smoke test


class TestFixtureIntegrity:
    """Verify the test fixture matches expected Noir OAS3 output shape."""

    def test_fixture_has_expected_paths(self) -> None:
        fixture = _FIXTURES / "noir_oas3.json"
        result = parse_noir_json(fixture)
        paths = {ep["path"] for ep in result["endpoints"]}
        assert "/login" in paths
        assert "/learn/vulnerability/{vuln}" in paths
        assert "/bulkproducts" in paths

    def test_fixture_login_has_post_with_body_params(self) -> None:
        fixture = _FIXTURES / "noir_oas3.json"
        result = parse_noir_json(fixture)
        login_posts = [
            ep
            for ep in result["endpoints"]
            if ep["path"] == "/login" and ep["method"] == "POST"
        ]
        assert len(login_posts) == 1
        assert len(login_posts[0]["body_params"]) >= 2

    def test_fixture_path_param_endpoint_extracted(self) -> None:
        fixture = _FIXTURES / "noir_oas3.json"
        result = parse_noir_json(fixture)
        vuln_eps = [
            ep
            for ep in result["endpoints"]
            if ep["path"] == "/learn/vulnerability/{vuln}"
        ]
        assert len(vuln_eps) == 1
        assert vuln_eps[0]["path_params"][0]["name"] == "vuln"
