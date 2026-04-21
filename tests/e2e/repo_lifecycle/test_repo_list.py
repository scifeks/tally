"""E2E tests for the `repo list` command."""

from __future__ import annotations

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.repo_lifecycle.conftest import add_repo, create_setup

pytestmark = pytest.mark.local_only


def test_repo_list_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("repo list")
    assert "No active project" in output


def test_repo_list_empty(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_setup(h)

    output = h.run("repo list")

    assert "No repositories configured" in output


def test_repo_list_shows_repos(
    tally_harness: TallyHarness,
    tmp_path: object,
) -> None:
    from pathlib import Path

    h = tally_harness
    repo_path = Path(str(tmp_path)) / "myrepo"
    repo_path.mkdir()
    create_setup(h)
    add_repo(h, repo_path, name="listed-repo")

    output = h.run("repo list")

    assert "listed-repo" in output


def test_repo_list_live_dvpa(tally_harness_live: TallyHarness) -> None:
    h = tally_harness_live
    h.run("project switch DVPA")

    output = h.run("repo list")

    assert "dvwa" in output
    assert "dvpwa" in output
