"""Unit tests for LLM endpoint extraction and conversion."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from application.url_inventory.llm_extractor import (
    LlmEndpointExtractor,
    parse_extraction_response,
    to_url_findings,
)
from domain.url_inventory.entry import UrlSource, UrlTool


class TestParseExtractionResponse:
    def test_parses_valid_json(self) -> None:
        text = '{"endpoints": [{"method": "GET", "path": "/foo"}]}'
        result = parse_extraction_response(text)

        assert len(result) == 1
        assert result[0]["method"] == "GET"
        assert result[0]["path"] == "/foo"

    def test_handles_code_fence(self) -> None:
        text = """Here's the endpoints:
```json
{"endpoints": [{"method": "POST", "path": "/users"}]}
```
Some other text"""
        result = parse_extraction_response(text)

        assert len(result) == 1
        assert result[0]["method"] == "POST"
        assert result[0]["path"] == "/users"

    def test_empty_endpoints(self) -> None:
        text = '{"endpoints": []}'
        result = parse_extraction_response(text)

        assert result == []

    def test_invalid_json_returns_empty(self) -> None:
        text = "not json at all"
        result = parse_extraction_response(text)

        assert result == []

    def test_filters_invalid_methods(self) -> None:
        text = """{
            "endpoints": [
                {"method": "GET", "path": "/foo"},
                {"method": "INVALID", "path": "/bar"},
                {"method": "DELETE", "path": "/baz"}
            ]
        }"""
        result = parse_extraction_response(text)

        methods = [e["method"] for e in result]
        assert "GET" in methods
        assert "DELETE" in methods
        assert "INVALID" not in methods

    def test_normalizes_method_case(self) -> None:
        text = """{
            "endpoints": [
                {"method": "get", "path": "/foo"},
                {"method": "Post", "path": "/bar"}
            ]
        }"""
        result = parse_extraction_response(text)

        assert result[0]["method"] == "GET"
        assert result[1]["method"] == "POST"

    def test_defaults_missing_params(self) -> None:
        text = '{"endpoints": [{"method": "GET", "path": "/foo"}]}'
        result = parse_extraction_response(text)

        assert "query_params" in result[0]
        assert result[0]["query_params"] == []
        assert "form_params" in result[0]
        assert result[0]["form_params"] == []

    def test_preserves_existing_params(self) -> None:
        text = """{
            "endpoints": [{
                "method": "GET",
                "path": "/users",
                "query_params": ["page", "limit"],
                "form_params": ["name"]
            }]
        }"""
        result = parse_extraction_response(text)

        assert result[0]["query_params"] == ["page", "limit"]
        assert result[0]["form_params"] == ["name"]

    def test_finds_json_in_embedded_text(self) -> None:
        text = """Some explanation here.
{"endpoints": [{"method": "GET", "path": "/api"}]} and more text"""
        result = parse_extraction_response(text)

        assert len(result) == 1
        assert result[0]["method"] == "GET"


class TestToUrlFindings:
    def test_converts_to_url_findings(self) -> None:
        endpoints = [{"method": "GET", "path": "/users", "query_params": ["page"]}]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=42,
            host="example.com",
            port=443,
            protocol="https",
        )

        assert len(result) == 1
        finding = result[0]
        assert finding.repo_id == 1
        assert finding.run_id == 42
        assert finding.method == "GET"
        assert finding.path == "/users"
        assert finding.host == "example.com"
        assert finding.port == 443
        assert finding.protocol == "https"

    def test_sets_correct_source_and_tool(self) -> None:
        endpoints = [{"method": "GET", "path": "/"}]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=None,
            host="example.com",
            port=443,
            protocol="https",
        )

        assert result[0].source == UrlSource.SCAN
        assert result[0].tool == UrlTool.LLM

    def test_includes_query_params_in_meta(self) -> None:
        endpoints = [
            {"method": "GET", "path": "/users", "query_params": ["page", "limit"]}
        ]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        meta = result[0].meta
        params = meta["original_file"]["parameters"]
        query_params = [p for p in params if p.get("in") == "query"]

        assert len(query_params) == 2
        assert {"name": "page", "in": "query"} in query_params
        assert {"name": "limit", "in": "query"} in query_params

    def test_includes_form_params_in_meta(self) -> None:
        endpoints = [
            {
                "method": "POST",
                "path": "/users",
                "form_params": ["name", "email"],
            }
        ]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        meta = result[0].meta
        params = meta["original_file"]["parameters"]
        form_params = [p for p in params if p.get("in") == "formData"]

        assert len(form_params) == 2
        assert {"name": "name", "in": "formData"} in form_params
        assert {"name": "email", "in": "formData"} in form_params

    def test_includes_path_params_in_meta(self) -> None:
        endpoints = [{"method": "GET", "path": "/users/{user_id}/posts/{post_id}"}]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        meta = result[0].meta
        params = meta["original_file"]["parameters"]
        path_params = [p for p in params if p.get("in") == "path"]

        assert len(path_params) == 2
        assert {"name": "user_id", "in": "path"} in path_params
        assert {"name": "post_id", "in": "path"} in path_params

    def test_combines_all_param_types(self) -> None:
        endpoints = [
            {
                "method": "POST",
                "path": "/api/{version}/users",
                "query_params": ["filter"],
                "form_params": ["name"],
            }
        ]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        meta = result[0].meta
        params = meta["original_file"]["parameters"]

        query_params = [p for p in params if p.get("in") == "query"]
        form_params = [p for p in params if p.get("in") == "formData"]
        path_params = [p for p in params if p.get("in") == "path"]

        assert len(query_params) == 1
        assert len(form_params) == 1
        assert len(path_params) == 1

    def test_empty_endpoints(self) -> None:
        result = to_url_findings(
            [],
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        assert result == []

    def test_multiple_endpoints(self) -> None:
        endpoints = [
            {"method": "GET", "path": "/users"},
            {"method": "POST", "path": "/users"},
            {"method": "DELETE", "path": "/users/{id}"},
        ]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        assert len(result) == 3
        methods = [f.method for f in result]
        assert methods == ["GET", "POST", "DELETE"]

    def test_extracts_path_params_not_in_provided_list(self) -> None:
        """Path params from {braces} in path should be included even if
        not in form_params or query_params list."""
        endpoints = [
            {
                "method": "GET",
                "path": "/items/{item_id}",
                "query_params": [],
                "form_params": [],
            }
        ]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        params = result[0].meta["original_file"]["parameters"]
        assert len(params) == 1
        assert params[0] == {"name": "item_id", "in": "path"}

    def test_no_duplicate_path_params(self) -> None:
        """If same param name appears multiple times in path, include only once."""
        endpoints = [{"method": "GET", "path": "/items/{id}/subitems/{id}"}]
        result = to_url_findings(
            endpoints,
            repo_id=1,
            run_id=1,
            host="example.com",
            port=443,
            protocol="https",
        )

        params = result[0].meta["original_file"]["parameters"]
        path_params = [p for p in params if p.get("in") == "path"]
        assert len(path_params) == 1
        assert path_params[0]["name"] == "id"


class TestLlmEndpointExtractor:
    def test_extract_stores_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            controller_file = Path(tmpdir) / "controllers" / "UserController.py"
            controller_file.parent.mkdir(parents=True)
            controller_file.write_text("def get_users(): pass\n")

            mock_llm = MagicMock()
            mock_llm.complete.return_value = (
                '{"endpoints": '
                '[{"method": "GET", "path": "/users"}, '
                '{"method": "POST", "path": "/users"}]}'
            )

            mock_repo = MagicMock()
            mock_repo.insert_many.return_value = 2

            extractor = LlmEndpointExtractor(mock_llm, mock_repo)
            count = extractor.extract_for_repo(
                repo_path=tmpdir,
                repo_id=1,
                run_id=None,
                host="localhost",
                port=8000,
                protocol="http",
            )

            assert count == 2
            mock_llm.complete.assert_called_once()
            mock_repo.delete_for_repo_and_tool.assert_called_once_with(1, UrlTool.LLM)
            mock_repo.insert_many.assert_called_once()

    def test_extract_skips_when_no_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_llm = MagicMock()
            mock_repo = MagicMock()

            extractor = LlmEndpointExtractor(mock_llm, mock_repo)
            count = extractor.extract_for_repo(
                repo_path=tmpdir,
                repo_id=1,
                run_id=None,
                host="localhost",
                port=8000,
                protocol="http",
            )

            assert count == 0
            mock_llm.complete.assert_not_called()

    def test_extract_batches_large_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            controller_dir = Path(tmpdir) / "controllers"
            controller_dir.mkdir()

            for i in range(10):
                file_path = controller_dir / f"Controller{i}.py"
                file_path.write_text("x" * 5000)

            mock_llm = MagicMock()
            mock_llm.complete.return_value = (
                '{"endpoints": [{"method": "GET", "path": "/test"}]}'
            )

            mock_repo = MagicMock()
            mock_repo.insert_many.return_value = 1

            extractor = LlmEndpointExtractor(
                mock_llm, mock_repo, max_chars_per_batch=15000
            )
            count = extractor.extract_for_repo(
                repo_path=tmpdir,
                repo_id=1,
                run_id=None,
                host="localhost",
                port=8000,
                protocol="http",
            )

            assert mock_llm.complete.call_count > 1
            assert count >= 0

    def test_extract_handles_llm_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            controller_file = Path(tmpdir) / "controllers" / "Controller.py"
            controller_file.parent.mkdir(parents=True)
            controller_file.write_text("def get(): pass\n")

            mock_llm = MagicMock()
            mock_llm.complete.side_effect = Exception("LLM error")

            mock_repo = MagicMock()

            extractor = LlmEndpointExtractor(mock_llm, mock_repo)
            count = extractor.extract_for_repo(
                repo_path=tmpdir,
                repo_id=1,
                run_id=None,
                host="localhost",
                port=8000,
                protocol="http",
            )

            assert count == 0

    def test_extract_deduplicates_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            controller_dir = Path(tmpdir) / "controllers"
            controller_dir.mkdir()
            (controller_dir / "Controller1.py").write_text("x" * 100)
            (controller_dir / "Controller2.py").write_text("y" * 100)

            mock_llm = MagicMock()
            mock_llm.complete.return_value = (
                '{"endpoints": [{"method": "GET", "path": "/api/users"}]}'
            )

            mock_repo = MagicMock()
            mock_repo.insert_many.return_value = 1

            extractor = LlmEndpointExtractor(
                mock_llm, mock_repo, max_chars_per_batch=150
            )
            count = extractor.extract_for_repo(
                repo_path=tmpdir,
                repo_id=1,
                run_id=None,
                host="localhost",
                port=8000,
                protocol="http",
            )

            assert count == 1
            inserted_findings = mock_repo.insert_many.call_args[0][0]
            assert len(list(inserted_findings)) == 1
