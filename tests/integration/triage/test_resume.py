"""Integration tests for the triage resume path.

Verifies that resume_triage_for_project picks up rate_limited and
pending batches with a new billing method, and that completed batches
are left untouched.
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.triage_agent import (  # noqa: E402
    PreparedTriageSession,
)
from application.triage.factory import ResolvedTriageConfig  # noqa: E402
from application.triage.orchestrator import (  # noqa: E402
    resume_triage_for_project,
)
from application.triage.verdict import Verdict  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from tests.finding_helpers import normalize_test_findings  # noqa: E402

pytestmark = pytest.mark.integration

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "repo": "testrepo",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "potential",
    "file_path": "src/app.py",
    "rule_id": "python.sqli",
    "description": "SQL injection",
}


def _make_verdict(finding_id: int) -> Verdict:
    return Verdict(
        finding_id=finding_id,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="high",
        reasoning="test",
        remediation="fix",
        attack_vector="network",
        access_required="none",
        exploitation_complexity="low",
        user_interaction="none",
        call_stack=[],
    )


class _StubBackend:
    """Returns canned Verdicts."""

    @contextmanager
    def prepare_session(self, *, project, run_id, app_root):
        yield PreparedTriageSession(cwd=app_root)

    def run_triage(self, prompt, *, finding_id, timeout_seconds, cwd):
        return _make_verdict(finding_id)


def _make_tool_registry() -> MagicMock:
    tool = MagicMock()
    tool.name = "semgrep"
    tool.skip = False
    tool.scan_segment = "sast"
    reg = MagicMock()
    reg.get_tool.return_value = tool
    reg.get_all_tools.return_value = []
    return reg


def _seed_repo(factory: ConnectionFactory, name: str = "testrepo") -> int:
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, path) VALUES (?, ?)",
            (name, "/tmp/fakerepo"),
        )
        return cur.lastrowid  # type: ignore[return-value]


def _seed_findings_and_batches(
    factory: ConnectionFactory,
    run_id: int,
    repo_id: int,
    batch_statuses: list[tuple[str | None, str | None]],
    finding_repo,
) -> list[int]:
    """Seed findings and create batches with prescribed statuses.

    ``batch_statuses`` is a list of ``(batch_status, usage_pool)`` pairs.
    Each pair gets one finding and one batch. When ``batch_status`` is
    None the batch stays pending with no execution row.

    Returns the batch IDs in insertion order.
    """
    findings_per_batch: list[dict] = []
    for i in range(len(batch_statuses)):
        findings_per_batch.append(
            {
                **_BASE_FINDING,
                "file_path": f"src/file{i}.py",
                "repo_id": repo_id,
            }
        )
    finding_repo.insert_findings(run_id, normalize_test_findings(findings_per_batch))

    with factory.connect() as conn:
        fids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM findings WHERE run_id = ? ORDER BY id",
                (run_id,),
            ).fetchall()
        ]

    batch_ids: list[int] = []
    with factory.connect() as conn:
        for idx, (status, usage_pool) in enumerate(batch_statuses):
            fid = fids[idx]
            batch_data = json.dumps(
                [
                    {
                        **_BASE_FINDING,
                        "id": fid,
                        "file_path": f"src/file{idx}.py",
                        "repo_id": repo_id,
                        "segment": "sast",
                    }
                ]
            )
            fid_json = json.dumps([fid])

            batch_status = status if status is not None else "pending"
            started_at = "datetime('now')" if status is not None else "NULL"
            completed_at = (
                "datetime('now')"
                if status in ("completed", "failed", "rate_limited")
                else "NULL"
            )
            cur = conn.execute(
                f"INSERT INTO triage_batches"
                f"  (run_id, finding_ids, batch_data, status,"
                f"   run_attempts, started_at, completed_at)"
                f" VALUES"
                f"  (?, ?, ?, ?, ?, {started_at}, {completed_at})",
                (
                    run_id,
                    fid_json,
                    batch_data,
                    batch_status,
                    1 if status is not None else 0,
                ),
            )
            batch_id: int = cur.lastrowid  # type: ignore[assignment]
            batch_ids.append(batch_id)

            if status is not None:
                conn.execute(
                    """
                    INSERT INTO triage_batch_executions
                        (batch_id, attempt_number, status, usage_pool,
                         started_at, finished_at)
                    VALUES (?, 1, ?, ?, datetime('now'), datetime('now'))
                    """,
                    (batch_id, status, usage_pool),
                )

    return batch_ids


def _count_executions(factory: ConnectionFactory, batch_id: int) -> int:
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM triage_batch_executions WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
    return row["cnt"]


def _latest_usage_pool(factory: ConnectionFactory, batch_id: int) -> str | None:
    with factory.connect() as conn:
        row = conn.execute(
            """
            SELECT usage_pool FROM triage_batch_executions
            WHERE batch_id = ?
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (batch_id,),
        ).fetchone()
    return row["usage_pool"] if row else None


_RESOLVED_API = ResolvedTriageConfig(
    provider_name="claude_sdk",
    base_url="",
    model="test-model",
    timeout_seconds=300,
    retry_count=0,
    debug=False,
    billing_method="api",
    api_key_source="test-key",
)


@pytest.fixture()
def project_env(tmp_path: Path):
    """Set up a project directory, config, and seeded DB.

    Returns (project_name, tmp_root, factory, run_repo, finding_repo,
    triage_repo, audit_repo, run_id, repo_id).
    """
    project = "test-project"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "test-model",
                },
                "triage_inference": {"provider": "ollama"},
            }
        )
    )

    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_path, project)
    factory = ConnectionFactory(
        tmp_path / "projects" / project / "sqlite" / "findings.db"
    )
    repo_id = _seed_repo(factory)
    run_id = run_repo.create_run({})
    return (
        project,
        tmp_path,
        factory,
        run_repo,
        finding_repo,
        triage_repo,
        audit_repo,
        run_id,
        repo_id,
    )


def test_resume_picks_up_rate_limited_batches(project_env) -> None:
    (
        project,
        tmp_root,
        factory,
        run_repo,
        finding_repo,
        triage_repo,
        audit_repo,
        run_id,
        repo_id,
    ) = project_env

    batch_ids = _seed_findings_and_batches(
        factory,
        run_id,
        repo_id,
        [
            ("completed", "plan"),
            ("rate_limited", "plan"),
            (None, None),
        ],
        finding_repo,
    )

    with patch("application.triage.factory.TriageAgentFactory") as mock_factory:
        mock_factory.return_value.create.return_value = _StubBackend()
        resume_triage_for_project(
            project,
            project_id=1,
            scan_run_id=run_id,
            tool_registry=_make_tool_registry(),
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={"testrepo": Path("/tmp/fakerepo")},
            app_root=tmp_root,
            resolved_config=_RESOLVED_API,
        )

    assert _count_executions(factory, batch_ids[0]) == 1
    assert _latest_usage_pool(factory, batch_ids[1]) == "api"
    assert _latest_usage_pool(factory, batch_ids[2]) == "api"


def test_resume_leaves_completed_batch_untouched(project_env) -> None:
    (
        project,
        tmp_root,
        factory,
        run_repo,
        finding_repo,
        triage_repo,
        audit_repo,
        run_id,
        repo_id,
    ) = project_env

    batch_ids = _seed_findings_and_batches(
        factory,
        run_id,
        repo_id,
        [
            ("completed", "plan"),
            ("rate_limited", "plan"),
        ],
        finding_repo,
    )

    with patch("application.triage.factory.TriageAgentFactory") as mock_factory:
        mock_factory.return_value.create.return_value = _StubBackend()
        resume_triage_for_project(
            project,
            project_id=1,
            scan_run_id=run_id,
            tool_registry=_make_tool_registry(),
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={"testrepo": Path("/tmp/fakerepo")},
            app_root=tmp_root,
            resolved_config=_RESOLVED_API,
        )

    with factory.connect() as conn:
        row = conn.execute(
            "SELECT status FROM triage_batches WHERE id = ?",
            (batch_ids[0],),
        ).fetchone()
    assert row["status"] == "completed"
    assert _latest_usage_pool(factory, batch_ids[0]) == "plan"


def test_single_batch_rate_limited_run_is_resumable(project_env) -> None:
    """A run whose only batch is rate_limited summarizes as rate_limited
    and TriageService.resume_triage accepts it without raising.
    """
    (
        project,
        tmp_root,
        factory,
        run_repo,
        finding_repo,
        triage_repo,
        audit_repo,
        run_id,
        repo_id,
    ) = project_env

    _seed_findings_and_batches(
        factory,
        run_id,
        repo_id,
        [("rate_limited", "plan")],
        finding_repo,
    )

    summary = triage_repo.summarize_for_run(run_id)
    assert summary is not None
    assert summary.status == "rate_limited"

    from application.triage.triage_service import TriageService

    service = TriageService(
        run_repo=run_repo,
        triage_repo=triage_repo,
        finding_repo=finding_repo,
        audit_repo=audit_repo,
    )
    with (
        patch("application.triage.triage_service.ConfigManager") as mock_cm,
        patch(
            "application.triage.triage_service.BackgroundModeAvailabilityService"
        ) as mock_avail_cls,
        patch(
            "application.triage.triage_service.resolve_triage_config",
            return_value=_RESOLVED_API,
        ),
    ):
        cfg = MagicMock()
        cfg.claude.default_billing_method = None
        cfg.claude.api_key = "test-key"
        mock_cm.return_value.global_config = cfg
        avail = MagicMock()
        avail.oauth_available = True
        avail.api_key_available = True
        mock_avail_cls.return_value.evaluate.return_value = avail

        with patch.object(service, "_dispatch") as mock_dispatch:
            mock_dispatch.return_value = MagicMock(scan_run_id=run_id)
            service.resume_triage(
                base_path=str(tmp_root),
                project_id=1,
                project_name=project,
                scan_run_id=run_id,
                tool_registry=_make_tool_registry(),
                interaction_mode="background",
                billing_method="api",
                api_key="sk-x",
            )

            rc = mock_dispatch.call_args.kwargs["resolved_config"]
            assert rc.provider_name == "claude_sdk"
            assert rc.billing_method == "api"
            assert rc.api_key_source == "sk-x"


def test_resume_failed_batches_get_new_execution(project_env) -> None:
    (
        project,
        tmp_root,
        factory,
        run_repo,
        finding_repo,
        triage_repo,
        audit_repo,
        run_id,
        repo_id,
    ) = project_env

    batch_ids = _seed_findings_and_batches(
        factory,
        run_id,
        repo_id,
        [
            ("failed", "plan"),
        ],
        finding_repo,
    )

    with patch("application.triage.factory.TriageAgentFactory") as mock_factory:
        mock_factory.return_value.create.return_value = _StubBackend()
        resume_triage_for_project(
            project,
            project_id=1,
            scan_run_id=run_id,
            tool_registry=_make_tool_registry(),
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={"testrepo": Path("/tmp/fakerepo")},
            app_root=tmp_root,
            resolved_config=_RESOLVED_API,
        )

    assert _count_executions(factory, batch_ids[0]) == 2
    assert _latest_usage_pool(factory, batch_ids[0]) == "api"
