"""Tests for ``application/repl/commands/_repo_label.py``."""

from __future__ import annotations

from types import SimpleNamespace

from application.repl.commands._repo_label import build_repos_by_id, label_for


class TestBuildReposById:
    def test_collects_id_to_name(self) -> None:
        repos = [
            SimpleNamespace(id=1, name="api"),
            SimpleNamespace(id=2, name="web"),
        ]
        assert build_repos_by_id(repos) == {1: "api", 2: "web"}

    def test_skips_missing_id(self) -> None:
        repos = [
            SimpleNamespace(name="api"),
            SimpleNamespace(id=2, name="web"),
        ]
        assert build_repos_by_id(repos) == {2: "web"}

    def test_skips_missing_name(self) -> None:
        repos = [
            SimpleNamespace(id=1, name=""),
            SimpleNamespace(id=2, name="web"),
        ]
        assert build_repos_by_id(repos) == {2: "web"}

    def test_skips_non_int_id(self) -> None:
        repos = [SimpleNamespace(id="not-int", name="api")]
        assert build_repos_by_id(repos) == {}

    def test_empty_input(self) -> None:
        assert build_repos_by_id([]) == {}


class TestLabelFor:
    def test_returns_name_for_known_id(self) -> None:
        assert label_for(1, {1: "api", 2: "web"}) == "api"

    def test_returns_empty_for_unknown_id(self) -> None:
        assert label_for(99, {1: "api"}) == ""

    def test_returns_empty_for_none(self) -> None:
        assert label_for(None, {1: "api"}) == ""

    def test_coerces_string_int(self) -> None:
        assert label_for("1", {1: "api"}) == "api"

    def test_returns_empty_for_non_numeric_string(self) -> None:
        assert label_for("not-a-number", {1: "api"}) == ""

    def test_returns_empty_for_empty_lookup(self) -> None:
        assert label_for(1, {}) == ""
