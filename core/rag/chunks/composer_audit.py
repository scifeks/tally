"""ComposerAuditChunkBuilder — converts composer-audit ToolResults into chunks."""

from typing import Any

from core.tools.base import ToolResult

from .sca import _build_sca_chunks, _sca_fingerprint_key


class ComposerAuditChunkBuilder:
    tool_name = "composer-audit"
    domain = "code"
    provided_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return _build_sca_chunks(self, result, profile)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("composer-audit", finding)
