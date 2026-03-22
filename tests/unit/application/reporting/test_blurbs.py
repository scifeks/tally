"""Unit tests for application.reporting.blurbs."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.blurbs import (  # noqa: E402
    BlurbNotFoundError,
    BlurbVariableError,
    load_blurb,
)


@pytest.fixture()
def blurbs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temp blurbs directory and patch the module to use it."""
    import application.reporting.blurbs as blurbs_module

    monkeypatch.setattr(blurbs_module, "_BLURBS_DIR", tmp_path)
    return tmp_path


class TestLoadBlurb:
    def test_successful_substitution(self, blurbs_dir: Path) -> None:
        (blurbs_dir / "hello.md").write_text(
            "Dear {{name}}, welcome to {{place}}.", encoding="utf-8"
        )
        result = load_blurb("hello", {"name": "Alice", "place": "Wonderland"})
        assert result == "Dear Alice, welcome to Wonderland."

    def test_missing_file_raises_blurb_not_found_error(self, blurbs_dir: Path) -> None:
        with pytest.raises(BlurbNotFoundError):
            load_blurb("nonexistent")

    def test_missing_variable_raises_blurb_variable_error(
        self, blurbs_dir: Path
    ) -> None:
        (blurbs_dir / "tmpl.md").write_text(
            "Hello {{name}}, your code is {{code}}.", encoding="utf-8"
        )
        with pytest.raises(BlurbVariableError):
            load_blurb("tmpl", {"name": "Bob"})

    def test_extra_keys_in_variables_are_ignored(self, blurbs_dir: Path) -> None:
        (blurbs_dir / "simple.md").write_text("Value: {{val}}", encoding="utf-8")
        result = load_blurb("simple", {"val": "42", "unused": "ignored"})
        assert result == "Value: 42"

    def test_no_placeholders_no_variables_ok(self, blurbs_dir: Path) -> None:
        (blurbs_dir / "static.md").write_text("No placeholders here.", encoding="utf-8")
        result = load_blurb("static")
        assert result == "No placeholders here."

    def test_multiple_occurrences_of_same_placeholder(self, blurbs_dir: Path) -> None:
        (blurbs_dir / "repeat.md").write_text(
            "{{x}} and {{x}} again.", encoding="utf-8"
        )
        result = load_blurb("repeat", {"x": "foo"})
        assert result == "foo and foo again."

    def test_returns_string(self, blurbs_dir: Path) -> None:
        (blurbs_dir / "s.md").write_text("hello", encoding="utf-8")
        assert isinstance(load_blurb("s"), str)


class TestRealBlurbFiles:
    """Smoke tests against the actual shipped blurb files."""

    def test_confidentiality_substitution(self) -> None:
        result = load_blurb(
            "confidentiality",
            {
                "company_name": "Acme Corp",
                "engagement_date": "2025-06-01",
                "engagement_type": "white box",
            },
        )
        assert "Acme Corp" in result
        assert "2025-06-01" in result
        assert "white box" in result

    def test_severity_definitions_no_placeholders(self) -> None:
        result = load_blurb("severity-definitions")
        assert "Critical" in result
        assert "Informational" in result

    def test_tools_used_substitution(self) -> None:
        result = load_blurb("tools-used", {"tool_list": "- semgrep\n- gitleaks"})
        assert "semgrep" in result

    def test_testing_type_substitution(self) -> None:
        result = load_blurb(
            "testing-type",
            {
                "testing_type": "White Box",
                "testing_type_description": "Full access was provided.",
            },
        )
        assert "White Box" in result

    def test_glossary_no_placeholders(self) -> None:
        result = load_blurb("glossary")
        assert "Authentication" in result
        assert "Vulnerability" in result
