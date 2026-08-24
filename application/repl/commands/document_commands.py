"""REPL commands for managing project documents."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from domain.documents.chunker import chunk_text
from factories.llm import create_embedding_provider, create_vector_index

if TYPE_CHECKING:
    from application.rag.document_store import DocumentStore
    from application.repl.interface import REPL

_SUPPORTED_EXTENSIONS = {".md", ".txt"}


class DocumentCommands:
    def __init__(self, repl: REPL) -> None:
        self.repl = repl
        self._store_cache: dict[str, DocumentStore] = {}

    def cmd_docs(
        self,
        _cmd: str,
        args: list[str],
    ) -> None:
        sub = args[0] if args else "help"
        if sub == "add":
            self._add(args[1:])
        elif sub == "list":
            self._list()
        elif sub == "remove":
            self._remove(args[1:])
        elif sub == "stats":
            self._stats()
        else:
            self.repl.console.print(
                "[yellow]Usage:[/yellow] docs <add|list|remove|stats>"
            )

    def _get_store(self) -> DocumentStore | None:
        project = self.repl.active_project
        if not project:
            self.repl.console.print(
                "[red]No active project.[/red] Run 'project select <name>' first."
            )
            return None

        if project in self._store_cache:
            return self._store_cache[project]

        from application.rag.document_store import DocumentStore

        try:
            base = Path(self.repl.base_path)
            embedding = create_embedding_provider(base)
            index = create_vector_index(
                project_name=project,
                base_path=base,
                embedding_provider=embedding,
                collection_type="documents",
            )
            store = DocumentStore(index)
            self._store_cache[project] = store
            return store
        except Exception as exc:
            self.repl.console.print(f"[red]Document store unavailable:[/red] {exc}")
            return None

    def _add(self, args: list[str]) -> None:
        if not args:
            self.repl.console.print("[yellow]Usage:[/yellow] docs add <filepath>")
            return

        filepath = Path(args[0]).expanduser().resolve()
        if not filepath.exists():
            self.repl.console.print(f"[red]File not found:[/red] {filepath}")
            return

        if filepath.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            exts = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
            self.repl.console.print(
                "[red]Unsupported file type:[/red] "
                f"{filepath.suffix}. Supported: {exts}"
            )
            return

        store = self._get_store()
        if store is None:
            return

        try:
            text = filepath.read_text(encoding="utf-8")
        except Exception as exc:
            self.repl.console.print(f"[red]Failed to read file:[/red] {exc}")
            return

        chunks = chunk_text(text)
        if not chunks:
            self.repl.console.print("[yellow]File is empty or blank.[/yellow]")
            return

        count = store.add_chunks(filepath.name, chunks)
        self.repl.console.print(
            f"[green]Added:[/green] {filepath.name} ({count} chunks)"
        )

    def _list(self) -> None:
        store = self._get_store()
        if store is None:
            return

        sources = store.list_sources()
        if not sources:
            self.repl.console.print("[yellow]No documents ingested.[/yellow]")
            return

        for src in sources:
            self.repl.console.print(f"  {src['name']} ({src['chunks']} chunks)")

    def _remove(self, args: list[str]) -> None:
        if not args:
            self.repl.console.print("[yellow]Usage:[/yellow] docs remove <filename>")
            return

        store = self._get_store()
        if store is None:
            return

        removed = store.remove_by_filename(args[0])
        if removed:
            self.repl.console.print(
                f"[green]Removed:[/green] {args[0]} ({removed} chunks)"
            )
        else:
            self.repl.console.print(f"[yellow]No document found:[/yellow] {args[0]}")

    def _stats(self) -> None:
        store = self._get_store()
        if store is None:
            return

        total = store.count()
        self.repl.console.print(f"[green]Documents:[/green] {total} chunks stored")
