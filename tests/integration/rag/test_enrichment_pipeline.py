"""Integration tests for EnrichmentPipeline (real SQLite)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import ProjectManager  # noqa: E402
from application.rag import EnrichmentPipeline  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.repositories.findings_serial import (  # noqa: E402
    compute_fingerprint,
)

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _write_commands_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "commands.json").write_text(
        json.dumps(
            {
                "nmap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/nmap",
                },
                "gitleaks": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/local/bin/gitleaks",
                },
                "zap": {
                    "type": "repo",
                    "location": "local",
                    "path": "/usr/bin/zap",
                },
            }
        )
    )


def _make_llm_response(fields: list[str]) -> dict:
    values = {
        "risk_type": "exposed_service",
        "remediation": "Restrict access to this port via firewall rules.",
        "severity": "potential",
        "description": (
            "An open port was found exposing a potentially exploitable service."
        ),
    }
    return {f: values[f] for f in fields if f in values}


def _seed(finding_repo: object, run_id: int, rows: list[dict]) -> list[int]:
    """Insert findings and return their SQLite ids."""
    finding_repo.upsert_findings(run_id, rows)  # type: ignore[union-attr]
    fps = [compute_fingerprint(r) for r in rows]
    return finding_repo.get_ids_by_fingerprints(fps)  # type: ignore[union-attr]


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    _write_commands_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    run_repo, finding_repo, _, _ = make_store(str(tmp_path), name)
    run_id = run_repo.create_run({})
    return {
        "base_path": tmp_path,
        "project_name": name,
        "run_repo": run_repo,
        "finding_repo": finding_repo,
        "run_id": run_id,
    }


_GL_ROW = {
    "tool": "gitleaks",
    "profile": "default",
    "finding_type": json.dumps(["secret"]),
    "severity": "high",
    "confidence": "confirmed",
    "description": "Leaked AWS access key found in config.py",
}
_ZAP_ROW = {
    "tool": "zap",
    "profile": "default",
    "finding_type": json.dumps(["vulnerability"]),
    "severity": "high",
    "description": "XSS via search param.",
    "remediation": "Encode output.",
    "alert_name": "Reflected XSS",
}
_NMAP_ROW = {
    "tool": "nmap",
    "profile": "default",
    "finding_type": json.dumps(["reconnaissance"]),
    "severity": "informational",
    "risk_type": "exposed_service",
}


@pytest.fixture()
def seeded_env(project_env: dict) -> dict:
    finding_repo = project_env["finding_repo"]
    run_id = project_env["run_id"]
    gl_ids = _seed(finding_repo, run_id, [_GL_ROW])
    zap_ids = _seed(finding_repo, run_id, [_ZAP_ROW])
    nmap_ids = _seed(finding_repo, run_id, [_NMAP_ROW])
    # Mark nmap as already enriched
    with finding_repo._factory.connect() as conn:
        conn.execute("UPDATE findings SET enriched = 1 WHERE id = ?", (nmap_ids[0],))
    return {
        **project_env,
        "gl_id": gl_ids[0],
        "zap_id": zap_ids[0],
        "nmap_id": nmap_ids[0],
    }


@pytest.fixture()
def pipeline(seeded_env: dict) -> EnrichmentPipeline:
    return EnrichmentPipeline(
        finding_repo=seeded_env["finding_repo"],
        base_path=str(seeded_env["base_path"]),
    )


class TestEnrichmentPipeline:
    def test_empty_ids_no_llm_call(self, pipeline: EnrichmentPipeline) -> None:
        with patch.object(pipeline, "_call_llm") as mock_llm:
            pipeline.enrich([])
            mock_llm.assert_not_called()

    def test_already_enriched_skipped(
        self, pipeline: EnrichmentPipeline, seeded_env: dict
    ) -> None:
        with patch.object(pipeline, "_call_llm") as mock_llm:
            pipeline.enrich([seeded_env["nmap_id"]])
            mock_llm.assert_not_called()

    def test_all_tool_provided_no_llm_call(self, project_env: dict) -> None:
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "zap",
            "profile": "default",
            "finding_type": json.dumps(["vulnerability"]),
            "severity": "high",
            "confidence": "probable",
            "remediation": "Use parameterized queries.",
            "description": "SQL injection found in login form.",
            "alert_name": "SQL Injection",
            "owasp_name": "Injection",
            "title": "SQL Injection in login form",
        }
        ids = _seed(finding_repo, run_id, [row])
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich(ids)
            mock_llm.assert_not_called()

    def test_missing_fields_calls_per_field(
        self, pipeline: EnrichmentPipeline, seeded_env: dict
    ) -> None:
        # zap-row uses the per-field path (ZapChunkBuilder has enrichment_fields)
        with patch.object(
            pipeline,
            "_call_per_field",
            return_value={"owasp_name": "Injection"},
        ) as mock_pf:
            pipeline.enrich([seeded_env["zap_id"]])
            mock_pf.assert_called_once()

    def test_enriched_true_after_success(
        self, pipeline: EnrichmentPipeline, seeded_env: dict
    ) -> None:
        with patch.object(
            pipeline, "_call_per_field", return_value={"owasp_name": "Injection"}
        ):
            pipeline.enrich([seeded_env["zap_id"]])
        row = seeded_env["finding_repo"].get_finding(seeded_env["zap_id"])
        assert row is not None
        assert row["enriched"] == 1

    def test_enriched_fields_written_to_metadata(
        self, pipeline: EnrichmentPipeline, seeded_env: dict
    ) -> None:
        # zap uses the per-field path; ZAP enriches owasp_name
        with patch.object(
            pipeline, "_call_per_field", return_value={"owasp_name": "Injection"}
        ):
            pipeline.enrich([seeded_env["zap_id"]])
        row = seeded_env["finding_repo"].get_finding(seeded_env["zap_id"])
        assert row is not None
        meta = json.loads(row["meta"] or "{}")
        assert meta.get("owasp_name") == "Injection"

    def test_invalid_json_leaves_enriched_false(
        self, pipeline: EnrichmentPipeline, seeded_env: dict
    ) -> None:
        with patch.object(
            pipeline,
            "_call_per_field",
            side_effect=json.JSONDecodeError("err", "", 0),
        ):
            pipeline.enrich([seeded_env["zap_id"]])
        row = seeded_env["finding_repo"].get_finding(seeded_env["zap_id"])
        assert row is not None
        assert row["enriched"] == 0

    def test_pipeline_continues_after_one_failure(self, project_env: dict) -> None:
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        rows = [
            {
                "tool": "semgrep",
                "profile": "default",
                "finding_type": json.dumps(["vulnerability"]),
                "severity": "medium",
                "description": "Finding A",
                "rule_id": "rule-A",
                "file_path": "a.py",
            },
            {
                "tool": "semgrep",
                "profile": "default",
                "finding_type": json.dumps(["vulnerability"]),
                "severity": "medium",
                "description": "Finding B",
                "rule_id": "rule-B",
                "file_path": "b.py",
            },
        ]
        ids = _seed(finding_repo, run_id, rows)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )

        call_count = [0]

        def side_effect(meta: dict, specs: list) -> dict:
            call_count[0] += 1
            if call_count[0] == 1:
                raise json.JSONDecodeError("bad", "", 0)
            return {"risk_type": "injection"}

        with patch.object(p, "_call_per_field", side_effect=side_effect):
            p.enrich(ids)

        # At least one succeeded (the non-failing one has enriched=1)
        enriched = [
            r
            for fid in ids
            if (r := finding_repo.get_finding(fid)) and r["enriched"] == 1
        ]
        assert len(enriched) >= 1

    def test_idempotent_second_run_skips(
        self, pipeline: EnrichmentPipeline, seeded_env: dict
    ) -> None:
        # zap uses the per-field path
        with patch.object(
            pipeline, "_call_per_field", return_value={"owasp_name": "Injection"}
        ) as mock_pf:
            pipeline.enrich([seeded_env["zap_id"]])
            pipeline.enrich([seeded_env["zap_id"]])
            assert mock_pf.call_count == 1

    def test_zap_skips_remediation_severity_description(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "zap"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == ["owasp_name", "title"]

    def test_gitleaks_skips_severity_and_risk_type(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "gitleaks"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == []

    def test_nmap_no_fields_to_enrich(self, pipeline: EnrichmentPipeline) -> None:
        metadata = {"tool": "nmap"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert fields == []

    def test_skips_field_if_already_has_value(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "nmap", "risk_type": "exposed_service"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "risk_type" not in fields

    def test_invalid_severity_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"severity": "CRITICAL", "risk_type": "xss"}
        result = pipeline._validate_response(raw, ["severity", "risk_type"])
        assert "severity" not in result
        assert result.get("risk_type") == "xss"

    def test_non_snake_case_risk_type_omitted(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        raw = {"risk_type": "Cross Site Scripting"}
        result = pipeline._validate_response(raw, ["risk_type"])
        assert "risk_type" not in result

    def test_unexpected_fields_ignored(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"risk_type": "xss", "evil_field": "x"}
        result = pipeline._validate_response(raw, ["risk_type"])
        assert "evil_field" not in result
        assert result.get("risk_type") == "xss"

    def test_empty_string_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"risk_type": ""}
        result = pipeline._validate_response(raw, ["risk_type"])
        assert "risk_type" not in result

    def test_valid_response_passes_through(self, pipeline: EnrichmentPipeline) -> None:
        raw = {
            "risk_type": "exposed_service",
            "remediation": "Block the port via firewall.",
            "severity": "medium",
            "confidence": "probable",
            "description": "Port 22 is open and accessible.",
        }
        fields = list(raw.keys())
        result = pipeline._validate_response(raw, fields)
        assert result == raw

    def test_invalid_confidence_omitted(self, pipeline: EnrichmentPipeline) -> None:
        raw = {"confidence": "high"}
        result = pipeline._validate_response(raw, ["confidence"])
        assert "confidence" not in result

    def test_valid_confidence_passes_through(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        raw = {"confidence": "confirmed"}
        result = pipeline._validate_response(raw, ["confidence"])
        assert result.get("confidence") == "confirmed"

    def test_gitleaks_skips_confidence(self, pipeline: EnrichmentPipeline) -> None:
        metadata = {"tool": "gitleaks"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "confidence" not in fields

    def test_semgrep_confidence_requested_from_llm(
        self, pipeline: EnrichmentPipeline
    ) -> None:
        metadata = {"tool": "semgrep"}
        fields = pipeline._get_fields_to_enrich(metadata)
        assert "confidence" in fields
