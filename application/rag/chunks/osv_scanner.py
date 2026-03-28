"""OsvScannerHandler — converts osv-scanner ToolResults into finding dicts."""

from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from .sca import _SCA_OSV_ENRICHMENT_FIELDS, _build_sca_normalize, _sca_render


class OsvScannerHandler:
    tool_name = "osv-scanner"
    domain = "code"
    segment = "sca"
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = _SCA_OSV_ENRICHMENT_FIELDS
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }
    should_enrich = True

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        return _build_sca_normalize(self, result, profile)

    def render(self, row: dict) -> str:
        return _sca_render(row)
