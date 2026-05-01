"""Phase 3 integration tests: EnrichmentPipeline reads/writes SQLite only."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.rag.enrichment import EnrichmentPipeline
from infrastructure.store import make_store

pytestmark = pytest.mark.integration


def _seed_finding(
    finding_repo: object,
    run_id: int,
    tool: str,
    enriched: int = 0,
    extra: dict | None = None,
) -> int:
    """Insert a minimal finding and return its SQLite id."""
    row: dict = {
        "tool": tool,
        "profile": "default",
        "finding_type": json.dumps(["vulnerability"]),
        "severity": "high",
        "description": f"Test finding for {tool}",
    }
    if extra:
        row.update(extra)
    finding_repo.insert_findings(run_id, [row])  # type: ignore[union-attr]
    from domain.pipeline.fingerprint import compute_fingerprint

    fps = [compute_fingerprint(row)]
    ids = finding_repo.get_ids_by_fingerprints(fps)  # type: ignore[union-attr]
    if enriched:
        with finding_repo._factory.connect() as conn:  # type: ignore[union-attr]
            conn.execute(
                "UPDATE findings SET enriched = ? WHERE id = ?",
                (enriched, ids[0]),
            )
    return ids[0]


@pytest.fixture()
def store_env(tmp_path: Path) -> dict:
    """Create a real SQLite store in a temp directory."""
    run_repo, finding_repo, _, _ = make_store(str(tmp_path), "test-proj")
    run_id = run_repo.create_run({})
    return {
        "base_path": str(tmp_path),
        "project_name": "test-proj",
        "run_repo": run_repo,
        "finding_repo": finding_repo,
        "run_id": run_id,
    }


class TestPhase3EnrichmentReadsFromSQLite:
    def test_get_by_ids_returns_deserialized_rows(self, store_env: dict) -> None:
        """get_by_ids returns dicts with all named columns and meta fields."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        rows = finding_repo.get_by_ids([fid])

        assert len(rows) == 1
        assert rows[0]["tool"] == "semgrep"
        assert rows[0]["id"] == fid

    def test_get_by_ids_missing_id_silently_omitted(self, store_env: dict) -> None:
        """Missing IDs are silently skipped in get_by_ids."""
        finding_repo = store_env["finding_repo"]
        rows = finding_repo.get_by_ids([99999])
        assert rows == []

    def test_get_by_ids_empty_list_returns_empty(self, store_env: dict) -> None:
        finding_repo = store_env["finding_repo"]
        rows = finding_repo.get_by_ids([])
        assert rows == []


class TestPhase3EnrichmentSkipsAlreadyEnriched:
    def test_already_enriched_row_not_sent_to_llm(self, store_env: dict) -> None:
        """Rows with enriched=1 are skipped; LLM provider is not called."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep", enriched=1)

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )

        pipeline.enrich([fid])

        mock_llm.complete.assert_not_called()

    def test_unenriched_row_triggers_llm(self, store_env: dict) -> None:
        """Rows with enriched=0 go through the LLM enrichment path."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )
        with patch.object(
            pipeline,
            "_call_per_field",
            return_value={"risk_type": "injection"},
        ) as mock_pf:
            pipeline.enrich([fid])

        mock_pf.assert_called_once()


class TestPhase3EnrichmentWritesToSQLite:
    def test_update_enrichment_fields_sets_enriched_1(self, store_env: dict) -> None:
        """After enrich(), the SQLite row has enriched=1."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )
        with patch.object(
            pipeline,
            "_call_per_field",
            return_value={"risk_type": "sql_injection"},
        ):
            pipeline.enrich([fid])

        row = finding_repo.get_finding(fid)
        assert row is not None
        assert row["enriched"] == 1

    def test_enrichment_fields_written_to_meta(self, store_env: dict) -> None:
        """LLM-returned fields like risk_type land in the meta blob."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )
        with patch.object(
            pipeline,
            "_call_per_field",
            return_value={"risk_type": "xss", "remediation": "Encode output."},
        ):
            pipeline.enrich([fid])

        row = finding_repo.get_finding(fid)
        assert row is not None
        meta = json.loads(row["meta"] or "{}")
        assert meta["risk_type"] == "xss"
        assert meta["remediation"] == "Encode output."

    def test_named_column_fields_written_directly(self, store_env: dict) -> None:
        """Fields like description are written to the named column."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )
        with patch.object(
            pipeline,
            "_call_per_field",
            return_value={"description": "SQL injection in login form."},
        ):
            pipeline.enrich([fid])

        row = finding_repo.get_finding(fid)
        assert row is not None
        assert row["description"] == "SQL injection in login form."


class TestPhase3ToolBypass:
    def test_nmap_no_llm_calls(self, store_env: dict) -> None:
        """nmap findings bypass LLM enrichment (should_enrich=False)."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "nmap")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )

        pipeline.enrich([fid])

        mock_llm.complete.assert_not_called()

    def test_gitleaks_no_llm_calls(self, store_env: dict) -> None:
        """gitleaks findings bypass LLM enrichment (should_enrich=False)."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "gitleaks")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )

        pipeline.enrich([fid])

        mock_llm.complete.assert_not_called()

    def test_semgrep_triggers_llm(self, store_env: dict) -> None:
        """semgrep findings are sent to LLM enrichment."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        mock_llm = MagicMock()
        pipeline = EnrichmentPipeline(
            finding_repo=finding_repo,
            base_path=store_env["base_path"],
            llm_provider=mock_llm,
        )
        with patch.object(
            pipeline,
            "_call_per_field",
            return_value={"risk_type": "injection"},
        ) as mock_pf:
            pipeline.enrich([fid])

        mock_pf.assert_called_once()


class TestPhase3UpdateEnrichmentFields:
    def test_update_enrichment_fields_sets_enriched_and_last_seen(
        self, store_env: dict
    ) -> None:
        """update_enrichment_fields sets enriched=1 and updates last_seen."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(finding_repo, run_id, "semgrep")

        finding_repo.update_enrichment_fields(fid, {"risk_type": "xss"})

        row = finding_repo.get_finding(fid)
        assert row is not None
        assert row["enriched"] == 1
        assert row["last_seen"] is not None

    def test_update_enrichment_fields_meta_merged(self, store_env: dict) -> None:
        """update_enrichment_fields merges into existing meta blob."""
        finding_repo = store_env["finding_repo"]
        run_id = store_env["run_id"]
        fid = _seed_finding(
            finding_repo, run_id, "semgrep", extra={"source_file": "scan.json"}
        )

        finding_repo.update_enrichment_fields(fid, {"owasp_name": "Injection"})

        row = finding_repo.get_finding(fid)
        assert row is not None
        meta = json.loads(row["meta"] or "{}")
        assert meta["owasp_name"] == "Injection"

    def test_update_enrichment_fields_missing_id_is_noop(self, store_env: dict) -> None:
        """update_enrichment_fields with a non-existent id does nothing."""
        finding_repo = store_env["finding_repo"]
        finding_repo.update_enrichment_fields(99999, {"risk_type": "xss"})
