"""Unit tests for EnrichmentPipeline cancellation during Phase 2.

When the cancel token is set while LLM workers are running, the
`as_completed` loop must:
  - shut down the executor (cancelling pending futures),
  - persist the findings whose enrichment already completed (Phase 3),
  - raise ScanCancelled so the orchestrator records `status='cancelled'`
    and emits RunCancelled.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from application.locking.cancellation import CancellationToken
from application.rag.enrichment import EnrichmentPipeline
from application.tools.orchestrator import ScanCancelled


def _row(id_: int) -> dict:
    return {"id": id_, "enriched": 0}


def test_cancel_during_phase2_raises_and_persists_completed_only() -> None:
    """Cancel after first finding finishes; only that finding is persisted."""
    repo = MagicMock()
    repo.get_by_ids.return_value = [_row(1), _row(2), _row(3)]

    token = CancellationToken()
    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=7,
        project_id=1,
        cancel_token=token,
    )
    pipeline._llm_provider = MagicMock()
    pipeline._resolve_max_workers = lambda: 1  # type: ignore[method-assign]
    pipeline._get_enrichment_plan = lambda row: (["title"], None)  # type: ignore[method-assign]

    call_lock = threading.Lock()
    call_count = {"n": 0}

    def _worker(*_args, **_kwargs):
        with call_lock:
            call_count["n"] += 1
            n = call_count["n"]
        if n == 1:
            # Cancel after the first finding completes; the as_completed
            # loop will see the token set on its next iteration.
            token.set()
        return {"title": f"finding-{n}"}

    pipeline._call_llm_worker = _worker  # type: ignore[method-assign]

    with pytest.raises(ScanCancelled):
        pipeline.enrich([1, 2, 3])

    # Phase 3 ran for whatever completed before the cancel was observed.
    # With max_workers=1 the first finding always completes before the
    # loop checks the token, so at least one update is persisted.
    assert repo.update_enrichment_fields.called
    persisted_ids = {c.args[0] for c in repo.update_enrichment_fields.call_args_list}
    assert 1 in persisted_ids
    # The third finding's worker must not have run (or its result must
    # have been discarded by executor.shutdown(cancel_futures=True)).
    assert 3 not in persisted_ids


def test_cancel_before_phase2_raises_immediately() -> None:
    """Token already set before enrich() — fires on first loop iteration."""
    repo = MagicMock()
    repo.get_by_ids.return_value = [_row(1), _row(2)]

    token = CancellationToken()
    token.set()  # pre-cancelled

    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=7,
        project_id=1,
        cancel_token=token,
    )
    pipeline._llm_provider = MagicMock()
    pipeline._resolve_max_workers = lambda: 1  # type: ignore[method-assign]
    pipeline._get_enrichment_plan = lambda row: (["title"], None)  # type: ignore[method-assign]
    pipeline._call_llm_worker = lambda *a, **kw: {"title": "x"}  # type: ignore[method-assign]

    with pytest.raises(ScanCancelled):
        pipeline.enrich([1, 2])


def test_no_cancel_token_runs_to_completion() -> None:
    """Default behaviour without a token: enrich completes normally."""
    repo = MagicMock()
    repo.get_by_ids.return_value = [_row(1), _row(2)]

    pipeline = EnrichmentPipeline(
        finding_repo=repo,
        run_id=7,
        project_id=1,
    )
    pipeline._llm_provider = MagicMock()
    pipeline._resolve_max_workers = lambda: 1  # type: ignore[method-assign]
    pipeline._get_enrichment_plan = lambda row: (["title"], None)  # type: ignore[method-assign]
    pipeline._call_llm_worker = lambda *a, **kw: {"title": "x"}  # type: ignore[method-assign]

    pipeline.enrich([1, 2])  # must not raise

    persisted_ids = {c.args[0] for c in repo.update_enrichment_fields.call_args_list}
    assert persisted_ids == {1, 2}
