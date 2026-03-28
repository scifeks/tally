"""Integration tests: nmap bypasses LLM enrichment entirely."""

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
from domain.pipeline.fingerprint import compute_fingerprint  # noqa: E402
from infrastructure.store import make_store  # noqa: E402

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


class TestNmapEnrichmentBypass:
    def test_nmap_zero_llm_calls(self, project_env: dict) -> None:
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "nmap",
            "profile": "default",
            "finding_type": json.dumps(["reconnaissance"]),
            "severity": "informational",
            "ip_address": "10.0.0.1",
            "port": "22",
        }
        fid = _seed(finding_repo, run_id, row)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        with patch.object(p, "_call_llm") as mock_llm:
            p.enrich([fid])
            mock_llm.assert_not_called()

    def test_nmap_enriched_stays_false_after_pipeline(self, project_env: dict) -> None:
        # nmap has should_enrich=False: the pipeline skips it, enriched stays 0
        finding_repo = project_env["finding_repo"]
        run_id = project_env["run_id"]
        row = {
            "tool": "nmap",
            "profile": "default",
            "finding_type": json.dumps(["reconnaissance"]),
            "severity": "informational",
            "ip_address": "10.0.0.1",
        }
        fid = _seed(finding_repo, run_id, row)
        p = EnrichmentPipeline(
            finding_repo=finding_repo, base_path=str(project_env["base_path"])
        )
        p.enrich([fid])
        db_row = finding_repo.get_finding(fid)
        assert db_row is not None
        assert db_row["enriched"] == 0

    def test_semgrep_still_calls_llm(self, project_env: dict) -> None:
        # semgrep uses the per-field path; verify enrichment runs (not skipped
        # like nmap) by checking _call_per_field is called.
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
        with patch.object(
            p, "_call_per_field", return_value={"risk_type": "sql_injection"}
        ) as mock_pf:
            p.enrich([fid])
            mock_pf.assert_called_once()

    def test_zap_still_calls_llm(self, project_env: dict) -> None:
        # zap uses the per-field path; verify enrichment runs (not skipped
        # like nmap) by checking _call_per_field is called.
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
