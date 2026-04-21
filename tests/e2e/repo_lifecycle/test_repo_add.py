"""E2E tests for the `repo add` command."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.repo_lifecycle.conftest import create_setup

pytestmark = pytest.mark.local_only


def test_repo_add_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("repo add")
    assert "No active project" in output


def test_repo_add_local_minimal(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)

    h.send("repo add")
    h.expect("Name")
    h.send("test-repo")
    h.expect("Type:")
    h.send("api")
    h.expect("Mode")
    h.send("")
    h.expect("Local path")
    h.send(str(repo_path))
    h.expect("Languages")
    h.send("")
    h.expect("Base URLs")
    h.send("")
    h.expect("Test dir")
    h.send("")
    h.expect("Ignore dir")
    h.send("")
    h.expect("Endpoint definition file")
    h.send("")
    output = h.wait_for_prompt()

    assert "test-repo" in output

    list_output = h.run("repo list")
    assert "test-repo" in list_output


def test_repo_add_empty_name_reprompts(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)

    h.send("repo add")
    h.expect("Name")
    h.send("")
    h.expect("name is required")
    h.send("valid-repo")
    h.expect("Type:")
    h.send("api")
    h.expect("Mode")
    h.send("")
    h.expect("Local path")
    h.send(str(repo_path))
    h.expect("Languages")
    h.send("")
    h.expect("Base URLs")
    h.send("")
    h.expect("Test dir")
    h.send("")
    h.expect("Ignore dir")
    h.send("")
    h.expect("Endpoint definition file")
    h.send("")
    output = h.wait_for_prompt()

    assert "valid-repo" in output


def test_repo_add_invalid_type_reprompts(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)

    h.send("repo add")
    h.expect("Name")
    h.send("test-repo")
    h.expect("Type:")
    h.send("invalid")
    h.expect("Invalid type")
    h.send("api")
    h.expect("Mode")
    h.send("")
    h.expect("Local path")
    h.send(str(repo_path))
    h.expect("Languages")
    h.send("")
    h.expect("Base URLs")
    h.send("")
    h.expect("Test dir")
    h.send("")
    h.expect("Ignore dir")
    h.send("")
    h.expect("Endpoint definition file")
    h.send("")
    h.wait_for_prompt()

    list_output = h.run("repo list")
    assert "test-repo" in list_output


def test_repo_add_nonexistent_path_reprompts(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    real_path = tmp_path / "myrepo"
    real_path.mkdir()
    create_setup(h)

    h.send("repo add")
    h.expect("Name")
    h.send("test-repo")
    h.expect("Type:")
    h.send("api")
    h.expect("Mode")
    h.send("")
    h.expect("Local path")
    h.send("/nonexistent/path/that/does/not/exist")
    h.expect("Path does not exist")
    h.send(str(real_path))
    h.expect("Languages")
    h.send("")
    h.expect("Base URLs")
    h.send("")
    h.expect("Test dir")
    h.send("")
    h.expect("Ignore dir")
    h.send("")
    h.expect("Endpoint definition file")
    h.send("")
    h.wait_for_prompt()

    list_output = h.run("repo list")
    assert "test-repo" in list_output


def test_repo_add_library_with_ui_rejected(
    tally_harness: TallyHarness,
    tmp_path: Path,
) -> None:
    h = tally_harness
    repo_path = tmp_path / "myrepo"
    repo_path.mkdir()
    create_setup(h)

    h.send("repo add")
    h.expect("Name")
    h.send("test-repo")
    h.expect("Type:")
    h.send("library,ui-old")
    h.expect("mutually exclusive")
    h.send("library")
    h.expect("Mode")
    h.send("")
    h.expect("Local path")
    h.send(str(repo_path))
    h.expect("Languages")
    h.send("")
    h.expect("Base URLs")
    h.send("")
    h.expect("Test dir")
    h.send("")
    h.expect("Ignore dir")
    h.send("")
    h.expect("Endpoint definition file")
    h.send("")
    h.wait_for_prompt()

    list_output = h.run("repo list")
    assert "test-repo" in list_output
