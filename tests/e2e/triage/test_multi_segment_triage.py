"""E2E multi-segment triage test.

Exercises the full triage pipeline across both SAST and web segments.
Seeds findings in both segments, starts real Docker triage containers
against local Ollama, invokes the triage agent, and verifies that
both findings are triaged with expected fields populated.

Requires: Docker, triage image, Ollama with a suitable model.
Skipped automatically if preconditions are not met.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.factory import TriageAgentFactory  # noqa: E402
from application.triage.runner import TriageRunner  # noqa: E402
from domain.tools.constants import CONFIDENCE_LEVELS  # noqa: E402
from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from tests.conftest import requires_docker  # noqa: E402

pytestmark = pytest.mark.e2e


# -- helper functions -------------------------------------------------------


def _make_tool_mock(name: str, segment: str) -> MagicMock:
    """Build a mock tool with name, skip=False, and scan_segment."""
    tool = MagicMock()
    tool.name = name
    tool.skip = False
    tool.scan_segment = segment
    return tool


def _build_registry() -> MagicMock:
    """Build a tool registry mock for semgrep (sast) and graphql-cop (web)."""
    registry = MagicMock()
    registry.get_all_tools.return_value = []

    def get_tool_impl(name: str) -> MagicMock:
        if name == "semgrep":
            return _make_tool_mock("semgrep", "sast")
        elif name == "graphql-cop":
            return _make_tool_mock("graphql-cop", "web")
        raise ValueError(f"unexpected tool: {name}")

    registry.get_tool.side_effect = get_tool_impl
    return registry


# -- test -------------------------------------------------------------------


@requires_docker
@pytest.mark.timeout(300)
def test_sast_and_web_findings_triaged(
    triage_env: dict[str, Any],
) -> None:
    """Triage both SAST and web findings in a single run.

    Verifies that both findings are enriched, triaged, assigned
    confidence levels, and have reasoning and remediation populated.
    """
    env = triage_env
    tmp_path: Path = env["tmp_path"]
    finding_ids: dict[str, int] = env["finding_ids"]
    factory: ConnectionFactory = env["factory"]

    registry = _build_registry()

    agent_factory = TriageAgentFactory(app_root=tmp_path)
    adapter = agent_factory.create()

    runner = TriageRunner(
        env["project"],
        env["run_repo"],
        env["triage_repo"],
        None,
        tmp_path,
        tool_registry=registry,
        triage_backend=adapter,
        session_timeout_seconds=180,
        finding_repo=env["finding_repo"],
        repo_paths=env["repo_paths"],
        triage_provider="opencode",
        triaged_by="auto_triage",
    )

    result = runner.run()
    assert result.success >= 2, "expected at least 2 findings triaged"

    for segment, finding_id in finding_ids.items():
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT enriched, triaged_at, triaged_by,"
                " confidence, meta"
                " FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()

        msg = f"[{segment}] finding {finding_id} not in DB"
        assert row is not None, msg

        msg_enriched = f"[{segment}] enriched not set"
        assert row["enriched"] == 1, msg_enriched

        msg_triaged_at = f"[{segment}] triaged_at is None"
        assert row["triaged_at"] is not None, msg_triaged_at

        msg_triaged_by = f"[{segment}] triaged_by != 'opencode'"
        assert row["triaged_by"] == "opencode", msg_triaged_by

        msg_confidence = (
            f"[{segment}] confidence {row['confidence']} not in CONFIDENCE_LEVELS"
        )
        assert row["confidence"] in CONFIDENCE_LEVELS, msg_confidence

        meta = json.loads(row["meta"] or "{}")
        triage_meta = meta.get("triage", {})

        msg_reasoning = f"[{segment}] reasoning is empty"
        assert triage_meta.get("reasoning"), msg_reasoning

        msg_remediation = f"[{segment}] remediation is empty"
        assert triage_meta.get("remediation"), msg_remediation
