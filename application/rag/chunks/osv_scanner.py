"""OsvScannerChunkBuilder — converts osv-scanner ToolResults into ChromaDB chunks."""

from typing import Any

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from .sca import _SCA_OSV_ENRICHMENT_FIELDS, _build_sca_chunks, _sca_fingerprint_key


class OsvScannerChunkBuilder:
    tool_name = "osv-scanner"
    domain = "code"
    segment = "sca"
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = _SCA_OSV_ENRICHMENT_FIELDS
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return _build_sca_chunks(self, result, profile)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return _sca_fingerprint_key("osv-scanner", finding)
