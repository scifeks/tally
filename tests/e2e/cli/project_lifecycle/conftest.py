"""Shared helpers for project lifecycle e2e tests."""

from __future__ import annotations

from tests.e2e.cli.harness import TallyHarness


def create_project(
    h: TallyHarness,
    name: str = "TestProj",
    company: str = "TestCo",
    abbreviation: str = "",
) -> str:
    """Drive the minimal project-creation wizard and return the project name."""
    h.send("project add")
    h.expect("Project name")
    h.send(name)
    h.expect("Add repositories")
    h.send("N")
    h.expect("Company Name")
    h.send(company)
    h.expect("Department Name")
    h.send("")
    h.expect("Abbreviation")
    h.send(abbreviation)
    h.wait_for_prompt()
    return name
