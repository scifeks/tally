"""Integration tests for LLM endpoint extraction pipeline.

Verifies that extracted endpoints flow through SQLite storage and reappear
in JIT-rebuilt seed files with query parameters intact.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.url_inventory.jit import jit_rebuild_artifacts  # noqa: E402
from application.url_inventory.llm_extractor import (  # noqa: E402
    LlmEndpointExtractor,
)
from core.config.schemas import Repository  # noqa: E402
from core.config.schemas.repo_service import RepoService  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.url_findings import (  # noqa: E402
    UrlFindingRepository,
)

pytestmark = pytest.mark.integration


class TestLlmEndpointExtraction:
    """LLM extraction pipeline: LLM → SQLite → JIT rebuild."""

    def test_extracted_urls_appear_in_jit_seeds(self, tmp_path: Path) -> None:
        """Full pipeline: extract endpoints, store in DB, rebuild seed file."""
        base = tmp_path
        project_name = "test-project"

        paths = ProjectPaths.from_canonical(str(base), project_name)
        paths.findings_db.parent.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()

        repo_dir = base / "repo-src"
        repo_dir.mkdir(exist_ok=True)

        with factory.connect() as conn:
            conn.execute(
                "INSERT INTO repositories (id, name, path) VALUES (?, ?, ?)",
                (1, "test-repo", str(repo_dir)),
            )

        url_repo = UrlFindingRepository(factory)

        (repo_dir / "app" / "Actions").mkdir(parents=True, exist_ok=True)
        (repo_dir / "app" / "Actions" / "ListUsers.php").write_text(
            "<?php\npublic function listUsers($page, $limit) {}\n"
        )

        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps(
            {
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/api/users",
                        "query_params": ["page", "limit"],
                        "form_params": [],
                    },
                    {
                        "method": "POST",
                        "path": "/api/users",
                        "query_params": [],
                        "form_params": ["name", "email"],
                    },
                ]
            }
        )

        extractor = LlmEndpointExtractor(mock_llm, url_repo)
        count = extractor.extract_for_repo(
            repo_path=str(repo_dir),
            repo_id=1,
            run_id=None,
            host="example.com",
            port=443,
            protocol="https",
        )
        assert count == 2

        repo = Repository(
            name="test-repo",
            path=str(repo_dir),
            id=1,
            services=[
                RepoService(
                    name="default",
                    base_urls=["https://example.com"],
                )
            ],
        )

        seeds_path, oas3_path = jit_rebuild_artifacts(
            str(base), project_name, repo, url_repo
        )

        assert seeds_path is not None
        assert seeds_path.endswith("merged_urls.txt")

        seeds_content = Path(seeds_path).read_text()
        assert "page=" in seeds_content
        assert "limit=" in seeds_content
        assert "/api/users" in seeds_content

    def test_extraction_with_no_url_inventory_returns_none_from_jit(
        self, tmp_path: Path
    ) -> None:
        """JIT rebuild returns (None, None) when no extraction rows exist."""
        base = tmp_path
        project_name = "test-project"

        paths = ProjectPaths.from_canonical(str(base), project_name)
        paths.findings_db.parent.mkdir(parents=True, exist_ok=True)

        factory = ConnectionFactory(paths.findings_db)
        factory.init_schema()

        url_repo = UrlFindingRepository(factory)

        repo_dir = base / "repo-src"
        repo_dir.mkdir(exist_ok=True)

        repo = Repository(
            name="test-repo",
            path=str(repo_dir),
            id=1,
            services=[
                RepoService(
                    name="default",
                    base_urls=["https://example.com"],
                )
            ],
        )

        seeds_path, oas3_path = jit_rebuild_artifacts(
            str(base), project_name, repo, url_repo
        )

        assert seeds_path is None
        assert oas3_path is None
