"""Shared helpers for repo lifecycle e2e tests."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.cli.harness import TallyHarness
from tests.e2e.cli.project_lifecycle.conftest import create_project


def create_setup(
    h: TallyHarness,
    name: str = "TestProj",
    company: str = "TestCo",
) -> str:
    """Create a project and switch to it; return the project name."""
    return create_project(h, name=name, company=company)


def add_repo(
    h: TallyHarness,
    repo_path: Path,
    name: str = "test-repo",
    repo_type: str = "api",
) -> str:
    """Drive the minimal repo-add wizard and return the repo name.

    Uses *repo_path* as the local path (must exist on disk).
    Sends empty input for all optional fields.
    """
    h.send("repo add")
    h.expect("Name")
    h.send(name)
    h.expect("Type:")
    h.send(repo_type)
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
    return name
