"""Draft/reviewed file resolver and markdown-to-HTML converter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.reporting.blurbs import load_blurb
from core.project_paths import ProjectPaths

if TYPE_CHECKING:
    from application.ports.draft_files import DraftFilesPort
    from application.ports.user_prompt import UserPromptPort


class SectionMissingError(Exception):
    """Raised when a section file cannot be found or the user declines a draft."""


class DraftResolver:
    """Resolve each report section to HTML, preferring reviewed over draft.

    Checks for reviewed sections first, then draft sections (with user prompt),
    then raises SectionMissingError. All text is converted from markdown to HTML.
    """

    def __init__(
        self,
        project: str,
        base_path: str | Path,
        prompt: UserPromptPort,
        draft_files: DraftFilesPort | None = None,
    ) -> None:
        paths = ProjectPaths.from_canonical(base_path, project)
        self._draft_dir = paths.reports_draft_dir
        self._reviewed_dir = paths.reports_dir / "reviewed"
        self._prompt = prompt
        self._draft_files = draft_files

    # Public API

    def resolve(self, section: str) -> str:
        """Return rendered HTML for the section.

        Raises:
            SectionMissingError: No usable file exists, or user declined a draft.
        """
        reviewed = self._reviewed_dir / f"{section}.md"

        if reviewed.exists():
            return self._md_to_html(reviewed.read_text(encoding="utf-8"))

        if self._draft_files:
            draft_text = self._draft_files.read(section)
        else:
            draft = self._draft_dir / f"{section}.md"
            draft_text = draft.read_text(encoding="utf-8") if draft.exists() else None

        if draft_text is None:
            raise SectionMissingError(
                f"No file found for section {section!r}. "
                f"Run 'report draft {section}' to generate a draft."
            )

        if not self._prompt.confirm(
            f"Section {section!r} has no reviewed copy. Proceed with draft?"
        ):
            raise SectionMissingError(
                f"Assembly halted: section {section!r} has no reviewed copy."
            )

        return self._md_to_html(draft_text)

    def resolve_blurb(self, name: str, variables: dict[str, str] | None = None) -> str:
        """Load blurb, substitute variables, and return HTML.

        Raises:
            BlurbNotFoundError: The blurb file does not exist.
            BlurbVariableError: A placeholder has no matching variable.
        """
        text = load_blurb(name, variables)
        return self._md_to_html(text)

    @staticmethod
    def _md_to_html(md_text: str) -> str:
        """Convert markdown text to an HTML fragment."""
        from markdown_it import MarkdownIt  # already installed via rich

        md = MarkdownIt()
        return md.render(md_text)


__all__ = ["DraftResolver", "SectionMissingError"]
