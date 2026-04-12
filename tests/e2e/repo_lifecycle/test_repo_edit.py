"""E2E tests for the `repo edit` command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.repo_lifecycle.conftest import add_repo, create_setup

pytestmark = pytest.mark.local_only


def test_repo_edit_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("repo edit test-repo")
    assert "No active project" in output


def test_repo_edit_no_name(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_setup(h)

    output = h.run("repo edit")

    assert "Usage" in output


def test_repo_edit_nonexistent(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_setup(h)

    output = h.run("repo edit nosuch")

    assert "not found" in output


def test_repo_edit_updates_type(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)
    add_repo(h, repo_path, name="test-repo", repo_type="api")

    h.send("repo edit test-repo")
    h.expect("Name")
    h.send("")
    h.expect(r"Type \[")
    h.send("api,ui")
    h.expect("Mode")
    h.send("")
    h.expect("Local path")
    h.send("")
    h.expect("Languages")
    h.send("")
    h.expect("Base URLs")
    h.send("http://localhost:8080")
    h.expect("Test dir")
    h.send("")
    h.expect("Ignore dir")
    h.send("")
    h.expect("Endpoint definition file")
    h.send("")
    output = h.wait_for_prompt()

    assert "updated" in output

    config_path = h.project_dir("TestProj") / "config" / "project.json"
    data = json.loads(config_path.read_text())
    repo = next(r for r in data["repositories"] if r["name"] == "test-repo")
    assert sorted(repo["type"]) == ["api", "ui"]
