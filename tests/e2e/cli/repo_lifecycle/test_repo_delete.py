"""E2E tests for the `repo delete` command."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.cli.harness import TallyHarness
from tests.e2e.cli.repo_lifecycle.conftest import add_repo, create_setup

pytestmark = pytest.mark.e2e


def test_repo_delete_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("repo delete test-repo")
    assert "No active project" in output


def test_repo_delete_no_name(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_setup(h)

    output = h.run("repo delete")

    assert "Usage" in output


def test_repo_delete_nonexistent(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_setup(h)

    h.send("repo delete nosuch")
    h.expect("Delete repository")
    h.send("y")
    output = h.wait_for_prompt()

    assert "not found" in output


def test_repo_delete_confirmed(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)
    add_repo(h, repo_path, name="delme")

    h.send("repo delete delme")
    h.expect("Delete repository")
    h.send("y")
    output = h.wait_for_prompt()

    assert "deleted" in output
    assert "delme" in output

    list_output = h.run("repo list")
    assert "No repositories configured" in list_output


def test_repo_delete_cancelled(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)
    add_repo(h, repo_path, name="keepme")

    h.send("repo delete keepme")
    h.expect("Delete repository")
    h.send("N")
    output = h.wait_for_prompt()

    assert "Cancelled" in output

    list_output = h.run("repo list")
    assert "keepme" in list_output
