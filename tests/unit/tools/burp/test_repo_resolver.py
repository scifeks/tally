"""Unit tests for URL-to-repo resolution."""

from __future__ import annotations

import pytest

from application.tools.burp.repo_resolver import resolve_repo_by_url
from core.config.schemas.repo_service import RepoService
from core.config.schemas.repository import Repository


def _repo(name: str, repo_id: int, base_urls: list[str]) -> Repository:
    svc = RepoService.model_construct(name=name, base_urls=base_urls)
    return Repository.model_construct(name=name, id=repo_id, services=[svc])


class TestResolveRepoByUrl:
    @pytest.mark.parametrize(
        "url, expected_name, expected_id",
        [
            pytest.param(
                "http://127.0.0.1:8081/WebGoat/login",
                "webgoat",
                1,
                id="exact-host-port-match",
            ),
            pytest.param(
                "http://127.0.0.1:8081/api/v2/items?q=test",
                "webgoat",
                1,
                id="path-after-base-matches",
            ),
            pytest.param(
                "http://10.0.0.5:9090/admin",
                "admin-panel",
                2,
                id="different-repo-match",
            ),
            pytest.param(
                "http://unknown.host:1234/foo",
                "",
                None,
                id="no-match",
            ),
            pytest.param(
                "",
                "",
                None,
                id="empty-url",
            ),
        ],
    )
    def test_resolve(
        self,
        url: str,
        expected_name: str,
        expected_id: int | None,
    ) -> None:
        repos = [
            _repo("webgoat", 1, ["http://127.0.0.1:8081"]),
            _repo(
                "admin-panel",
                2,
                ["http://10.0.0.5:9090"],
            ),
        ]
        name, rid = resolve_repo_by_url(url, repos)
        assert name == expected_name
        assert rid == expected_id

    def test_longest_prefix_wins(self) -> None:
        repos = [
            _repo("broad", 1, ["http://example.com"]),
            _repo(
                "specific",
                2,
                ["http://example.com/api/v2"],
            ),
        ]
        name, rid = resolve_repo_by_url(
            "http://example.com/api/v2/users",
            repos,
        )
        assert name == "specific"
        assert rid == 2

    def test_empty_repos_returns_no_match(self) -> None:
        name, rid = resolve_repo_by_url(
            "http://example.com/foo",
            [],
        )
        assert name == ""
        assert rid is None

    def test_trailing_slash_normalization(self) -> None:
        repos = [
            _repo("app", 1, ["http://example.com/"]),
        ]
        name, rid = resolve_repo_by_url(
            "http://example.com/path",
            repos,
        )
        assert name == "app"
        assert rid == 1
