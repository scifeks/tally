"""Unit tests: title enrichment field is declared for sast, api, and sca segments."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.rag import EnrichmentPipeline
from application.rag.chunks.semgrep import SemgrepHandler
from application.rag.chunks.zap import ZapHandler
from domain.tools.enrichment import PromptStrategy


def test_semgrep_title_in_enrichment_fields() -> None:
    builder = SemgrepHandler()
    spec = next((s for s in builder.enrichment_fields if s.field_name == "title"), None)
    assert spec is not None
    assert spec.strategy is PromptStrategy.GENERIC


def test_zap_title_in_enrichment_fields() -> None:
    builder = ZapHandler()
    spec = next((s for s in builder.enrichment_fields if s.field_name == "title"), None)
    assert spec is not None
    assert spec.strategy is PromptStrategy.GENERIC


@pytest.mark.parametrize(
    "tool_name",
    ["pip-audit", "npm-audit", "osv-scanner", "composer-audit"],
)
def test_sca_title_in_enrichment_fields(tool_name: str) -> None:
    pipeline = EnrichmentPipeline(MagicMock())
    legacy_fields, specs = pipeline._get_enrichment_plan(
        {"tool": tool_name, "enriched": False}
    )
    assert legacy_fields is None
    assert specs is not None
    assert any(s.field_name == "title" for s in specs)
    assert any(s.field_name == "owasp_name" for s in specs)
