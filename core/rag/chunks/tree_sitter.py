"""TreeSitterChunkBuilder — converts tree-sitter ToolResult into ChromaDB chunks."""

import json
from datetime import UTC, datetime
from typing import Any

from core.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta


class TreeSitterChunkBuilder:
    tool_name = "tree-sitter"
    domain = "structure"
    should_enrich = False
    non_enriched_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {"informational": {"type_informational"}}

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        file_records: list[dict[str, Any]] = parsed.get("files", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

        chunks: list[tuple[str, dict[str, Any], str]] = []

        for fi, record in enumerate(file_records):
            file_path = record.get("file_path", "")
            language = record.get("language", "")
            functions: list[dict[str, Any]] = record.get("functions", [])
            classes: list[dict[str, Any]] = record.get("classes", [])
            imports: list[str] = record.get("imports", [])
            calls: list[dict[str, Any]] = record.get("calls", [])
            assignments: list[dict[str, Any]] = record.get("assignments", [])

            # Build human-readable text for semantic search
            func_parts = [
                f"{f['name']}({f.get('parameters', '')})"
                f" [{f.get('start_line', 0)}-{f.get('end_line', 0)}]"
                for f in functions[:20]
            ]
            cls_parts = [
                f"{c['name']} [{c.get('start_line', 0)}-{c.get('end_line', 0)}]"
                for c in classes
            ]
            call_parts = [f"{c['callee']}:{c.get('line', 0)}" for c in calls[:30]]
            assign_parts = [f"{a['name']}:{a.get('line', 0)}" for a in assignments[:20]]

            text_lines = [
                f"[tree-sitter] structure {language}: {file_path}",
                f"Functions: {', '.join(func_parts) if func_parts else 'none'}",
                f"Classes: {', '.join(cls_parts) if cls_parts else 'none'}",
                f"Imports: {'; '.join(imports[:20]) if imports else 'none'}",
                f"Calls: {', '.join(call_parts) if call_parts else 'none'}",
                (f"Assignments: {', '.join(assign_parts) if assign_parts else 'none'}"),
            ]
            text = "\n".join(text_lines)

            meta: dict[str, Any] = {
                "tool": "tree-sitter",
                "profile": profile,
                "finding_type": json.dumps(["informational"]),
                "file_path": file_path,
                "language": language,
                "function_count": len(functions),
                "class_count": len(classes),
                "import_count": len(imports),
                "call_count": len(calls),
                "timestamp": timestamp,
                "source_file": source_file,
            }
            meta.update(_shared_meta(self, "informational"))

            doc_id = f"tree_sitter_{profile}_file_{fi}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return f"tree-sitter|{finding.get('file_path', '')}"
