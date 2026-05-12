"""Unit tests for garak JSONL parser."""

import json
import tempfile
from pathlib import Path
from typing import Any

from infrastructure.tools.parsers.garak import (
    GarakHandler,
    parse_garak_report,
)

_PLUGIN_CACHE: dict[str, Any] = {
    "entry_type": "plugin_cache",
    "run": "aaaa-bbbb",
    "plugin_cache": {
        "probes": {
            "probes.dan.DanInTheWild": {
                "description": "Jailbreak subset",
                "tags": [
                    "owasp:llm01",
                    "avid-effect:security:S0403",
                ],
                "goal": "bypass alignment",
                "primary_detector": ("mitigation.MitigationBypass"),
                "tier": 1,
            }
        },
        "detectors": {
            "detectors.mitigation.MitigationBypass": {
                "description": "Detects missing refusal",
                "hit_desc": "No refusal in response",
                "pass_desc": "Response refuses",
            }
        },
    },
}

_EVAL_FAIL: dict[str, Any] = {
    "entry_type": "eval",
    "probe": "dan.DanInTheWild",
    "detector": "mitigation.MitigationBypass",
    "passed": 200,
    "fails": 56,
    "nones": 0,
    "total_evaluated": 256,
    "total_processed": 256,
}

_EVAL_PASS: dict[str, Any] = {
    "entry_type": "eval",
    "probe": "encoding.InjectBase64",
    "detector": "mitigation.MitigationBypass",
    "passed": 256,
    "fails": 0,
    "nones": 0,
    "total_evaluated": 256,
    "total_processed": 256,
}


def _write_report(lines: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".report.jsonl",
        delete=False,
    )
    for line in lines:
        f.write(json.dumps(line) + "\n")
    f.close()
    return Path(f.name)


class TestParseGarakReport:
    def test_only_failed_evals_become_findings(self):
        path = _write_report([_PLUGIN_CACHE, _EVAL_FAIL, _EVAL_PASS])
        result = parse_garak_report(path)
        assert len(result["findings"]) == 1
        assert result["findings"][0]["probe"] == "dan.DanInTheWild"

    def test_finding_has_probe_metadata(self):
        path = _write_report([_PLUGIN_CACHE, _EVAL_FAIL])
        f = parse_garak_report(path)["findings"][0]
        assert f["goal"] == "bypass alignment"
        assert f["probe_description"] == "Jailbreak subset"
        assert f["probe_tier"] == 1
        assert "owasp:llm01" in f["tags"]

    def test_finding_has_detector_metadata(self):
        path = _write_report([_PLUGIN_CACHE, _EVAL_FAIL])
        f = parse_garak_report(path)["findings"][0]
        assert f["detector"] == "mitigation.MitigationBypass"
        assert f["detector_hit_desc"] == "No refusal in response"

    def test_finding_has_counts(self):
        path = _write_report([_PLUGIN_CACHE, _EVAL_FAIL])
        f = parse_garak_report(path)["findings"][0]
        assert f["fails"] == 56
        assert f["total_evaluated"] == 256

    def test_summary(self):
        path = _write_report([_PLUGIN_CACHE, _EVAL_FAIL, _EVAL_PASS])
        result = parse_garak_report(path)
        assert result["summary"]["total_findings"] == 1

    def test_empty_report(self):
        path = _write_report([{"entry_type": "init", "run": "x"}])
        result = parse_garak_report(path)
        assert result["findings"] == []
        assert result["summary"]["total_findings"] == 0

    def test_all_passing_evals_produce_no_findings(
        self,
    ):
        path = _write_report([_PLUGIN_CACHE, _EVAL_PASS])
        result = parse_garak_report(path)
        assert result["findings"] == []


class TestGarakHandlerAttributes:
    def test_tool_name(self):
        h = GarakHandler()
        assert h.tool_name == "garak"

    def test_segment(self):
        h = GarakHandler()
        assert h.segment == "llm"

    def test_owasp_is_non_enriched(self):
        h = GarakHandler()
        assert "owasp_name" in h.non_enriched_fields

    def test_enrichment_fields_set(self):
        h = GarakHandler()
        assert h.should_enrich is True
        assert h.enrichment_fields is not None
        field_names = {s.field_name for s in h.enrichment_fields}
        assert "risk_type" in field_names
        assert "title" in field_names
        assert "remediation" in field_names
        assert "owasp_name" not in field_names
