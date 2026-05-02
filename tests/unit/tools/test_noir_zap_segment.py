"""Tests for Noir/ZAP segment registration and scan ordering.

Covers:
- Both tools are registered in the 'web' segment
- Noir appears before ZAP in the ordered tool list for that segment
- Enrichment is NOT triggered for Noir; IS triggered for ZAP
"""

from __future__ import annotations

from unittest.mock import MagicMock

from application.tools.registry import ToolRegistry
from application.tools.scan_types.execution import ordered_repo_tools
from domain.tools.scan_types.models import SEGMENT_ORDER
from infrastructure.tools.wrappers.base.noir import BaseNoirTool
from infrastructure.tools.wrappers.base.zap import BaseZapTool

# Segment properties


class TestNoirSegmentRegistration:
    def test_noir_scan_segment_is_web(self) -> None:
        class _Noir(BaseNoirTool):
            def check_available(self) -> bool:
                return True

            def get_version(self):
                return None

            @property
            def command(self) -> str:
                return "noir"

            def build_command(self, **kwargs):
                return ["noir"]

        assert _Noir().scan_segment == "web"

    def test_zap_scan_segment_is_web(self) -> None:
        class _Zap(BaseZapTool):
            def check_available(self) -> bool:
                return True

            def get_version(self):
                return None

            @property
            def command(self) -> str:
                return "zap.sh"

            def build_command(self, **kwargs):
                return ["zap.sh"]

            def parse_output(self, output, files):
                return {}

            def build_execution_passes(self, context):
                return []

        assert _Zap().scan_segment == "web"

    def test_web_segment_in_segment_order(self) -> None:
        assert "web" in SEGMENT_ORDER

    def test_api_segment_not_in_segment_order(self) -> None:
        assert "api" not in SEGMENT_ORDER


# Ordering: noir must appear before zap within 'web' segment


class TestNoirZapOrdering:
    def _make_registry(self) -> ToolRegistry:
        """Build a minimal ToolRegistry with stub noir and zap entries."""
        registry = ToolRegistry()

        noir_stub = MagicMock()
        noir_stub.name = "noir"
        noir_stub.scan_segment = "web"

        zap_stub = MagicMock()
        zap_stub.name = "zap"
        zap_stub.scan_segment = "web"

        semgrep_stub = MagicMock()
        semgrep_stub.name = "semgrep"
        semgrep_stub.scan_segment = "sast"

        registry.register(noir_stub)
        registry.register(zap_stub)
        registry.register(semgrep_stub)
        return registry

    def test_noir_before_zap_in_ordered_tools(self) -> None:
        registry = self._make_registry()
        tool_set = {"noir", "zap", "semgrep"}
        ordered = ordered_repo_tools(tool_set, registry)
        assert "noir" in ordered
        assert "zap" in ordered
        assert ordered.index("noir") < ordered.index("zap")

    def test_web_segment_tools_appear_after_sast_in_order(self) -> None:
        registry = self._make_registry()
        tool_set = {"noir", "zap", "semgrep"}
        ordered = ordered_repo_tools(tool_set, registry)
        assert ordered.index("semgrep") < ordered.index("noir")
        assert ordered.index("semgrep") < ordered.index("zap")


# Enrichment skip: NoirHandler.should_enrich must be False


class TestNoirEnrichmentSkip:
    def test_noir_handler_should_enrich_is_false(self) -> None:
        from infrastructure.tools.parsers.noir import NoirHandler

        handler = NoirHandler()
        assert handler.should_enrich is False

    def test_noir_handler_enrichment_fields_is_none(self) -> None:
        from infrastructure.tools.parsers.noir import NoirHandler

        handler = NoirHandler()
        assert handler.enrichment_fields is None

    def test_enrichment_pipeline_skips_noir_rows(self) -> None:
        """EnrichmentPipeline._get_enrichment_plan returns empty list for noir."""

        from application.rag.enrichment import EnrichmentPipeline

        pipeline = EnrichmentPipeline(
            finding_repo=MagicMock(),
            base_path="/tmp",
        )
        row = {"tool": "noir", "enriched": 0, "url": "/api/test"}
        legacy, specs = pipeline._get_enrichment_plan(row)
        assert not legacy
        assert specs is None

    def test_zap_handler_should_enrich_is_true(self) -> None:
        """Confirm ZAP enrichment is still active after the segment change."""
        from infrastructure.tools.parsers.zap import ZapHandler

        handler = ZapHandler()
        assert handler.should_enrich is True
