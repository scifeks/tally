"""Filesystem adapter for draft markdown files."""

from __future__ import annotations

from pathlib import Path


class DraftFilesAdapter:
    """Reads and writes draft section markdown files."""

    def __init__(self, draft_dir: Path) -> None:
        self._dir = draft_dir

    def read(self, section: str) -> str | None:
        path = self._dir / f"{section}.md"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def write(self, section: str, content: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{section}.md"
        path.write_text(content, encoding="utf-8")

    def exists(self, section: str) -> bool:
        return (self._dir / f"{section}.md").exists()

    def delete(self, section: str) -> None:
        (self._dir / f"{section}.md").unlink(missing_ok=True)

    def ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
