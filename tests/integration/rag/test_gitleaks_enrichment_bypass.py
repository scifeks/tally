"""Integration tests: gitleaks bypasses LLM for risk_type entirely."""

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


def _seed(finding_repo: object, run_id: int, row: dict) -> int:
    finding_repo.upsert_findings(run_id, [row])  # type: ignore[union-attr]
    fps = [compute_fingerprint(row)]
    ids = finding_repo.get_ids_by_fingerprints(fps)  # type: ignore[union-attr]
    return ids[0]


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
        "finding_repo": finding_repo,
        "run_id": run_id,
    }


class TestGitleaksEnrichmentBypass:
    def test_gitleaks_with_rule_id_zero_llm_calls(self, project_env: dict) -> None:
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "gitleaks",
            "profile": "default",
            "finding_type": json.dumps(["secret"]),
            "severity": "high",
            "risk_type": "aws-access-token",
            "remediation": "Rotate the key and remove from repository.",
            "description": "AWS access token found in source file.",
        }
        fid = _seed(finding_repo, run_id, row)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich([fid])
            mock_llm.assert_not_called()

    def test_gitleaks_risk_type_not_requested_from_llm(self, project_env: dict) -> None:
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "gitleaks",
            "profile": "default",
            "finding_type": json.dumps(["secret"]),
            "severity": "high",
            "description": "Generic API key found in .env.",
        }
        fid = _seed(finding_repo, run_id, row)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        captured_fields: list[list[str]] = []

        def capture_call(doc_text: str, metadata: dict, fields: list) -> dict:
            captured_fields.append(list(fields))
            return {}

        with patch.object(p, "_call_llm", side_effect=capture_call):
            p.enrich([fid])

        assert not captured_fields, "LLM must not be called for gitleaks"

    def test_semgrep_still_receives_risk_type_from_llm(self, project_env: dict) -> None:
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "semgrep",
            "profile": "default",
            "finding_type": json.dumps(["vulnerability"]),
            "severity": "high",
            "description": "SQL injection in login.py line 42",
            "rule_id": "python.sqli",
            "file_path": "login.py",
        }
        fid = _seed(finding_repo, run_id, row)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        # semgrep uses the per-field path; verify _call_per_field fires and
        # the specs passed to it include risk_type.
        with patch.object(
            p, "_call_per_field", return_value={"risk_type": "sql_injection"}
        ) as mock_pf:
            p.enrich([fid])

        mock_pf.assert_called_once()
        call_specs = mock_pf.call_args[0][1]
        spec_names = [s.field_name for s in call_specs]
        assert "risk_type" in spec_names, "risk_type must be in semgrep specs"

    def test_zap_still_enriches_owasp_name(self, project_env: dict) -> None:
        # ZAP no longer enriches risk_type (always set from alert_name in metadata);
        # it enriches owasp_name via the DEDICATED per-field strategy.
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "zap",
            "profile": "default",
            "finding_type": json.dumps(["vulnerability"]),
            "severity": "high",
            "remediation": "Encode output.",
            "description": "XSS via search param.",
            "alert_name": "Reflected XSS",
        }
        fid = _seed(finding_repo, run_id, row)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        with patch.object(
            p, "_call_per_field", return_value={"owasp_name": "Injection"}
        ) as mock_pf:
            p.enrich([fid])

        mock_pf.assert_called_once()
        call_specs = mock_pf.call_args[0][1]
        spec_names = [s.field_name for s in call_specs]
        assert "owasp_name" in spec_names, "owasp_name must be in zap enrichment specs"
