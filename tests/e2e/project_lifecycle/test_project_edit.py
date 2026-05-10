"""E2E tests for the `project edit` command."""

from __future__ import annotations

import json

import pytest

from tests.e2e.harness import TallyHarness
from tests.e2e.project_lifecycle.conftest import create_project

pytestmark = pytest.mark.e2e


def test_project_edit_updates_fields(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="EditProj", company="OldCo", abbreviation="OLD")
    h.run("project switch EditProj")

    h.send("project edit")
    h.expect("Company Name")
    h.send("NewCo")
    h.expect("Department Name")
    h.send("Engineering")
    h.expect("Abbreviation")
    h.send("NEW")
    output = h.wait_for_prompt()

    assert "updated" in output

    config_path = h.project_dir("EditProj") / "config" / "project.json"
    data = json.loads(config_path.read_text())
    assert data["company_name"] == "NewCo"
    assert data["department_name"] == "Engineering"
    assert data["abbreviation"] == "NEW"


def test_project_edit_keep_defaults(tally_harness: TallyHarness) -> None:
    h = tally_harness
    create_project(h, name="KeepProj", company="KeepCo", abbreviation="KEP")
    h.run("project switch KeepProj")

    config_path = h.project_dir("KeepProj") / "config" / "project.json"
    before = config_path.read_text()

    h.send("project edit")
    h.expect("Company Name")
    h.send("")
    h.expect("Department Name")
    h.send("")
    h.expect("Abbreviation")
    h.send("")
    h.wait_for_prompt()

    after = config_path.read_text()
    assert json.loads(before) == json.loads(after)


def test_project_edit_no_active_project(tally_harness: TallyHarness) -> None:
    output = tally_harness.run("project edit")

    assert "No active project" in output
