"""PipAuditChunkBuilder — converts pip-audit ToolResults into ChromaDB chunks."""

from typing import Any

from core.tools.base import ToolResult

from .sca import _build_sca_chunks, _sca_fingerprint_key


class PipAuditChunkBuilder:
    tool_name = "pip-audit"

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return _build_sca_chunks("pip-audit", result, profile)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("pip-audit", finding)
