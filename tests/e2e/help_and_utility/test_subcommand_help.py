"""E2E tests for subcommand help: project, repo, tool, findings, search."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness

pytestmark = pytest.mark.local_only


def test_search_help_flag(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("search --help")
    assert "Search Syntax" in output
    assert "Global Filter Keys" in output


def test_project_no_args_shows_help(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project")
    assert "project add" in output
    assert "project switch" in output
    assert "project list" in output
    assert "project info" in output
    assert "project delete" in output


def test_repo_no_args_shows_help(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("repo")
    assert "repo add" in output
    assert "repo delete" in output
    assert "repo edit" in output
    assert "repo list" in output


def test_tool_no_args_shows_help(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool")
    assert "tool add" in output
    assert "tool edit" in output
    assert "tool remove" in output
    assert "tool list" in output


def test_findings_no_args_shows_help(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("findings")
    assert "findings visualize" in output
    assert "findings visualize --stop" in output


def test_project_unknown_subcommand(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project foobar")
    assert "Unknown subcommand" in output


def test_repo_unknown_subcommand(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("repo foobar")
    assert "Unknown subcommand" in output


def test_tool_unknown_subcommand(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("tool foobar")
    assert "Unknown subcommand" in output
