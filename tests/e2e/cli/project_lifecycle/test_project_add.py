"""E2E tests for the `project add` command."""

from __future__ import annotations

import json

import pytest

from tests.e2e.cli.harness import TallyHarness
from tests.e2e.cli.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.e2e


def test_project_add_minimal(tally_harness: TallyHarness) -> None:
    h = tally_harness

    h.send("project add")
    h.expect("Project name")
    h.send("TestProj")
    h.expect("Add repositories")
    h.send("N")
    h.expect("Company Name")
    h.send("TestCo")
    h.expect("Department Name")
    h.send("")
    h.expect("Abbreviation")
    h.send("TST")
    output = h.wait_for_prompt()

    assert "TestProj" in output

    list_output = h.run("project list")
    assert "TestProj" in list_output

    config_path = h.project_dir("TestProj") / "config" / "project.json"
    assert config_path.exists()


def test_project_add_empty_name_reprompts(tally_harness: TallyHarness) -> None:
    h = tally_harness

    h.send("project add")
    h.expect("Project name")
    h.send("")
    h.expect("Project name is required")
    h.send("ValidName")
    h.expect("Add repositories")
    h.send("N")
    h.expect("Company Name")
    h.send("Co")
    h.expect("Department Name")
    h.send("")
    h.expect("Abbreviation")
    h.send("")
    output = h.wait_for_prompt()

    assert "ValidName" in output


def test_project_add_invalid_name_reprompts(tally_harness: TallyHarness) -> None:
    h = tally_harness

    h.send("project add")
    h.expect("Project name")
    h.send("@invalid!")
    h.expect("Invalid name")
    h.send("GoodName")
    h.expect("Add repositories")
    h.send("N")
    h.expect("Company Name")
    h.send("Co")
    h.expect("Department Name")
    h.send("")
    h.expect("Abbreviation")
    h.send("")
    output = h.wait_for_prompt()

    assert "GoodName" in output


def test_project_add_duplicate_name(tally_harness: TallyHarness) -> None:
    h = tally_harness

    create_project(h, name="DupTest", company="Co")

    h.send("project add")
    h.expect("Project name")
    h.send("DupTest")
    output = h.wait_for_prompt()

    assert "already exists" in output


def test_project_add_creates_project_json(tally_harness: TallyHarness) -> None:
    create_project(tally_harness, name="JsonProj", company="JsonCo")

    config_path = tally_harness.project_dir("JsonProj") / "config" / "project.json"
    assert config_path.exists()
    data = json.loads(config_path.read_text())
    assert data["company_name"] == "JsonCo"
