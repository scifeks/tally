"""Unit tests for application.reporting.resolver."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.resolver import (  # noqa: E402
    DraftResolver,
    SectionMissingError,
)


class TestDraftResolverResolve:
    def test_reviewed_file_used_without_prompting(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reviewed file takes priority; no input() prompt is issued."""
        project = "acme"
        reviewed_dir = tmp_path / "projects" / project / "report" / "reviewed"
        reviewed_dir.mkdir(parents=True)
        (reviewed_dir / "executive-summary.md").write_text(
            "# Overview\n\nAll good.", encoding="utf-8"
        )

        called: list[str] = []
        monkeypatch.setattr("builtins.input", lambda _: called.append("called") or "n")

        resolver = DraftResolver(project, tmp_path)
        html = resolver.resolve("executive-summary")

        assert "<h1>" in html
        assert "All good" in html
        assert called == [], "input() must not be called when a reviewed file exists"

    def test_draft_used_when_user_confirms(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Draft file is used when the user answers 'y'."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "report" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "risk-level.md").write_text("**High**", encoding="utf-8")

        monkeypatch.setattr("builtins.input", lambda _: "y")

        resolver = DraftResolver(project, tmp_path)
        html = resolver.resolve("risk-level")

        assert "<strong>High</strong>" in html

    def test_draft_accepted_with_yes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full word 'yes' is also accepted."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "report" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "scope-and-methodology.md").write_text("Scope.", encoding="utf-8")

        monkeypatch.setattr("builtins.input", lambda _: "yes")

        resolver = DraftResolver(project, tmp_path)
        html = resolver.resolve("scope-and-methodology")

        assert "Scope" in html

    def test_draft_declined_raises_section_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """User answering 'n' raises SectionMissingError."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "report" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "critical-issues.md").write_text("Issues here.", encoding="utf-8")

        monkeypatch.setattr("builtins.input", lambda _: "n")

        resolver = DraftResolver(project, tmp_path)
        with pytest.raises(SectionMissingError, match="critical-issues"):
            resolver.resolve("critical-issues")

    def test_empty_answer_treated_as_no(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pressing Enter (empty string) is treated as 'N'."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "report" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "general-recommendations.md").write_text("Recs.", encoding="utf-8")

        monkeypatch.setattr("builtins.input", lambda _: "")

        resolver = DraftResolver(project, tmp_path)
        with pytest.raises(SectionMissingError):
            resolver.resolve("general-recommendations")

    def test_neither_file_raises_section_missing(self, tmp_path: Path) -> None:
        """SectionMissingError is raised immediately when no file exists."""
        project = "acme"
        # Ensure directory hierarchy exists but section file is absent
        (tmp_path / "projects" / project / "report").mkdir(parents=True)

        resolver = DraftResolver(project, tmp_path)
        with pytest.raises(SectionMissingError, match="improvement-points"):
            resolver.resolve("improvement-points")

    def test_reviewed_takes_priority_over_draft(self, tmp_path: Path) -> None:
        """Reviewed content wins even when a draft also exists."""
        project = "acme"
        report_root = tmp_path / "projects" / project / "report"
        draft_dir = report_root / "draft"
        reviewed_dir = report_root / "reviewed"
        draft_dir.mkdir(parents=True)
        reviewed_dir.mkdir(parents=True)

        (draft_dir / "executive-summary.md").write_text(
            "Draft content.", encoding="utf-8"
        )
        (reviewed_dir / "executive-summary.md").write_text(
            "Reviewed content.", encoding="utf-8"
        )

        with patch("builtins.input") as mock_input:
            resolver = DraftResolver(project, tmp_path)
            html = resolver.resolve("executive-summary")

        assert "Reviewed content" in html
        assert "Draft content" not in html
        mock_input.assert_not_called()


class TestDraftResolverMdToHtml:
    def test_markdown_headings_converted(self) -> None:
        assert "<h1>" in DraftResolver._md_to_html("# Title")

    def test_markdown_bold_converted(self) -> None:
        assert "<strong>" in DraftResolver._md_to_html("**bold**")

    def test_markdown_list_converted(self) -> None:
        html = DraftResolver._md_to_html("- item one\n- item two")
        assert "<ul>" in html
        assert "<li>" in html

    def test_returns_string(self) -> None:
        result = DraftResolver._md_to_html("plain text")
        assert isinstance(result, str)
        assert len(result) > 0


class TestDraftResolverResolveBlurb:
    def test_blurb_converted_to_html(self, tmp_path: Path) -> None:
        """resolve_blurb delegates to load_blurb and converts to HTML."""
        resolver = DraftResolver("acme", tmp_path)
        # Glossary has no required variables
        html = resolver.resolve_blurb("glossary")
        assert isinstance(html, str)
        assert len(html) > 0
        # Glossary blurb should contain some HTML markup
        assert "<" in html
