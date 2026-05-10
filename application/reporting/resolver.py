"""Draft/reviewed file resolver and markdown-to-HTML converter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from application.reporting.blurbs import load_blurb
from core.project_paths import ProjectPaths

if TYPE_CHECKING:
    from application.ports.user_prompt import UserPromptPort


class SectionMissingError(Exception):
    """Raised when a section file cannot be found or the user declines a draft."""


class DraftResolver:
    """Resolve each report section to HTML, preferring reviewed over draft.

    Resolution order for each section:
    1. ``projects/<project>/report/reviewed/<section>.md`` (used without prompting)
    2. ``projects/<project>/report/draft/<section>.md`` (user is prompted ``[y/N]``)
    3. Neither exists (raises :exc:`SectionMissingError` immediately)

    All resolved text is converted from markdown to HTML via
    :meth:`_md_to_html` before being returned.
    """

    def __init__(
        self, project: str, base_path: str | Path, prompt: UserPromptPort
    ) -> None:
        paths = ProjectPaths.from_canonical(base_path, project)
        self._draft_dir = paths.reports_draft_dir
        self._reviewed_dir = paths.reports_dir / "reviewed"
        self._prompt = prompt

    # Public API

    def resolve(self, section: str) -> str:
        """Return rendered HTML for *section*.

        Args:
            section: Section file stem, e.g. ``"executive-summary"``.

        Returns:
            HTML string (markdown converted).

        Raises:
            SectionMissingError: No usable file exists, or the user
                declined to proceed with a draft.
        """
        reviewed = self._reviewed_dir / f"{section}.md"
        draft = self._draft_dir / f"{section}.md"

        if reviewed.exists():
            return self._md_to_html(reviewed.read_text(encoding="utf-8"))

        if not draft.exists():
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

        return self._md_to_html(draft.read_text(encoding="utf-8"))

    def resolve_blurb(self, name: str, variables: dict[str, str] | None = None) -> str:
        """Load *name* blurb, substitute variables, and return HTML.

        Args:
            name:      Blurb name as understood by :func:`load_blurb`.
            variables: Placeholder substitutions to pass through.

        Returns:
            HTML string.

        Raises:
            BlurbNotFoundError: The blurb file does not exist.
            BlurbVariableError: A placeholder has no matching variable.
        """
        text = load_blurb(name, variables)
        return self._md_to_html(text)

    # Private helpers

    @staticmethod
    def _md_to_html(md_text: str) -> str:
        """Convert *md_text* (CommonMark markdown) to an HTML fragment."""
        from markdown_it import MarkdownIt  # already installed via rich

        md = MarkdownIt()
        return md.render(md_text)


__all__ = ["DraftResolver", "SectionMissingError"]
