"""NpmAuditChunkBuilder — converts npm-audit ToolResults into ChromaDB chunks."""

from typing import Any

from core.tools.base import ToolResult

from .sca import _build_sca_chunks, _sca_fingerprint_key


class NpmAuditChunkBuilder:
    tool_name = "npm-audit"
    domain = "code"
    segment = "sca"
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return _build_sca_chunks(self, result, profile)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("npm-audit", finding)
