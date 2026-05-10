"""Unit tests for application.reporting.resolver."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.resolver import (  # noqa: E402
    DraftResolver,
    SectionMissingError,
)


class _AlwaysConfirm:
    def confirm(self, question: str, *, default: bool = False) -> bool:
        return True

    def approve_all_remaining(self) -> None:
        pass


class _AlwaysDecline:
    def confirm(self, question: str, *, default: bool = False) -> bool:
        return False

    def approve_all_remaining(self) -> None:
        pass


class _SpyPrompt:
    def __init__(self) -> None:
        self.confirm_calls: list[str] = []

    def confirm(self, question: str, *, default: bool = False) -> bool:
        self.confirm_calls.append(question)
        return True

    def approve_all_remaining(self) -> None:
        pass


class TestDraftResolverResolve:
    def test_reviewed_file_used_without_prompting(self, tmp_path: Path) -> None:
        """Reviewed file takes priority; confirm() is never called."""
        project = "acme"
        reviewed_dir = tmp_path / "projects" / project / "reports" / "reviewed"
        reviewed_dir.mkdir(parents=True)
        (reviewed_dir / "executive-summary.md").write_text(
            "# Overview\n\nAll good.", encoding="utf-8"
        )

        spy = _SpyPrompt()
        resolver = DraftResolver(project, tmp_path, spy)
        html = resolver.resolve("executive-summary")

        assert "<h1>" in html
        assert "All good" in html
        assert spy.confirm_calls == [], (
            "confirm() must not be called for a reviewed file"
        )

    def test_draft_used_when_user_confirms(self, tmp_path: Path) -> None:
        """Draft file is used when the prompt confirms."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "risk-level.md").write_text("**High**", encoding="utf-8")

        resolver = DraftResolver(project, tmp_path, _AlwaysConfirm())
        html = resolver.resolve("risk-level")

        assert "<strong>High</strong>" in html

    def test_draft_accepted_when_confirm_returns_true(self, tmp_path: Path) -> None:
        """Draft is used whenever confirm() returns True."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "scope-and-methodology.md").write_text("Scope.", encoding="utf-8")

        resolver = DraftResolver(project, tmp_path, _AlwaysConfirm())
        html = resolver.resolve("scope-and-methodology")

        assert "Scope" in html

    def test_draft_declined_raises_section_missing(self, tmp_path: Path) -> None:
        """confirm() returning False raises SectionMissingError."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "critical-issues.md").write_text("Issues here.", encoding="utf-8")

        resolver = DraftResolver(project, tmp_path, _AlwaysDecline())
        with pytest.raises(SectionMissingError, match="critical-issues"):
            resolver.resolve("critical-issues")

    def test_decline_raises_section_missing(self, tmp_path: Path) -> None:
        """Any confirm()=False result raises SectionMissingError."""
        project = "acme"
        draft_dir = tmp_path / "projects" / project / "reports" / "draft"
        draft_dir.mkdir(parents=True)
        (draft_dir / "general-recommendations.md").write_text("Recs.", encoding="utf-8")

        resolver = DraftResolver(project, tmp_path, _AlwaysDecline())
        with pytest.raises(SectionMissingError):
            resolver.resolve("general-recommendations")

    def test_neither_file_raises_section_missing(self, tmp_path: Path) -> None:
        """SectionMissingError is raised immediately when no file exists."""
        project = "acme"
        (tmp_path / "projects" / project / "report").mkdir(parents=True)

        resolver = DraftResolver(project, tmp_path, _AlwaysConfirm())
        with pytest.raises(SectionMissingError, match="improvement-points"):
            resolver.resolve("improvement-points")

    def test_reviewed_takes_priority_over_draft(self, tmp_path: Path) -> None:
        """Reviewed content wins even when a draft also exists."""
        project = "acme"
        report_root = tmp_path / "projects" / project / "reports"
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

        spy = _SpyPrompt()
        resolver = DraftResolver(project, tmp_path, spy)
        html = resolver.resolve("executive-summary")

        assert "Reviewed content" in html
        assert "Draft content" not in html
        assert spy.confirm_calls == []


class TestDraftResolverMdToHtml:
    def test_markdown_headings_converted(self) -> None:
        assert "<h1>" in DraftResolver._md_to_html("# Title")

    def test_markdown_bold_converted(self) -> None:
        assert "<strong>" in DraftResolver._md_to_html("**bold**")

    def test_markdown_list_converted(self) -> None:
        html = DraftResolver._md_to_html("- item one\n- item two")
        assert "<ul>" in html
        assert "<li>" in html


class TestDraftResolverResolveBlurb:
    def test_blurb_converted_to_html(self, tmp_path: Path) -> None:
        """resolve_blurb delegates to load_blurb and converts to HTML."""
        resolver = DraftResolver("acme", tmp_path, _AlwaysConfirm())
        html = resolver.resolve_blurb("glossary")
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<" in html
