"""ComposerAuditChunkBuilder — converts composer-audit ToolResults into chunks."""

from typing import Any

from core.tools.base import ToolResult

from .sca import _build_sca_chunks, _sca_fingerprint_key


class ComposerAuditChunkBuilder:
    tool_name = "composer-audit"

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return _build_sca_chunks("composer-audit", result, profile)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("composer-audit", finding)
