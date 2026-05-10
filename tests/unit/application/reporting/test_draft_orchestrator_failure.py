"""Unit tests for draft generation failure handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from application.reporting import draft_orchestrator
from application.reporting.draft_orchestrator import (
    DraftCancelled,
    DraftGenerationError,
    DraftOverwriteDenied,
    DraftRequest,
    _user_message,
    run_draft,
)
from domain.pipeline.report_events import DraftFailed


@pytest.fixture
def request_obj(tmp_path: Path) -> DraftRequest:
    return DraftRequest(
        project="proj",
        base_path=tmp_path,
        section="executive-summary",
        force_overwrite=True,
        project_id=1,
    )


@pytest.fixture
def captured_events() -> list:
    return []


@pytest.fixture
def sink(captured_events: list) -> MagicMock:
    s = MagicMock()
    s.emit.side_effect = lambda evt: captured_events.append(evt)
    return s


@pytest.fixture
def repo() -> MagicMock:
    return MagicMock(get=MagicMock(return_value=None))


def _patch_generate(monkeypatch: pytest.MonkeyPatch, raiser) -> None:
    monkeypatch.setattr(draft_orchestrator, "_generate", raiser)


def test_mark_failed_called_with_user_facing_string(
    monkeypatch, request_obj, repo, sink, captured_events
):
    """DraftGenerationError forwarded to mark_failed."""

    def raiser(*_a, **_kw):
        raise DraftGenerationError("anything user-facing")

    _patch_generate(monkeypatch, raiser)

    with pytest.raises(DraftGenerationError):
        run_draft(
            request_obj,
            prompt=MagicMock(),
            repo=repo,
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            event_sink=sink,
        )

    repo.mark_failed.assert_called_once_with(
        "executive-summary", "anything user-facing"
    )
    failed = next(e for e in captured_events if isinstance(e, DraftFailed))
    assert failed.message == "anything user-facing"
    assert failed.error == "DraftGenerationError"


def test_no_findings_message_does_not_leak_should_report(
    monkeypatch, request_obj, repo, sink, captured_events
):
    """Error message does not expose internal column names."""

    def raiser(*_a, **_kw):
        raise DraftGenerationError(
            "No findings are marked for inclusion in the report. "
            "Triage your findings and mark which ones to include "
            "before generating drafts."
        )

    _patch_generate(monkeypatch, raiser)
    with pytest.raises(DraftGenerationError):
        run_draft(
            request_obj,
            prompt=MagicMock(),
            repo=repo,
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            event_sink=sink,
        )
    failed = next(e for e in captured_events if isinstance(e, DraftFailed))
    assert "should_report" not in failed.message
    assert "triaged_by" not in failed.message
    assert "No findings are marked" in failed.message


def test_unknown_exception_uses_generic_user_message(
    monkeypatch, request_obj, repo, sink, captured_events
):
    """Non-DraftGenerationError exceptions are wrapped in a generic prefix."""

    def raiser(*_a, **_kw):
        raise RuntimeError("internal stack")

    _patch_generate(monkeypatch, raiser)
    with pytest.raises(RuntimeError):
        run_draft(
            request_obj,
            prompt=MagicMock(),
            repo=repo,
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            event_sink=sink,
        )

    repo.mark_failed.assert_called_once()
    section, msg = repo.mark_failed.call_args.args
    assert section == "executive-summary"
    assert msg == "Draft generation failed: internal stack"
    failed = next(e for e in captured_events if isinstance(e, DraftFailed))
    assert failed.message == "Draft generation failed: internal stack"
    assert failed.error == "RuntimeError"


def test_cancelled_branch_persists_user_friendly_message(
    monkeypatch, request_obj, repo, sink, captured_events
):
    def raiser(*_a, **_kw):
        raise DraftCancelled("internal-cancel-detail")

    _patch_generate(monkeypatch, raiser)
    with pytest.raises(DraftCancelled):
        run_draft(
            request_obj,
            prompt=MagicMock(),
            repo=repo,
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            event_sink=sink,
        )

    repo.mark_failed.assert_called_once_with(
        "executive-summary", "Cancelled before generation completed."
    )
    failed = next(e for e in captured_events if isinstance(e, DraftFailed))
    assert failed.message == "Cancelled before generation completed."
    assert failed.error == "DraftCancelled"


def test_user_message_wraps_other_exceptions():
    assert _user_message(RuntimeError("x")) == "Draft generation failed: x"


def test_overwrite_denied_emits_failed_event(tmp_path, repo, sink, captured_events):
    """Pre-existing draft + force=False emits DraftFailed before raising.

    The web UI's SSE stream only learns about per-section state through
    these events; without an emit on the denied path the cards stay
    stuck in 'generating' forever.
    """
    section = "executive-summary"
    draft_dir = tmp_path / "projects" / "proj" / "reports" / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / f"{section}.md").write_text("stale", encoding="utf-8")

    request_obj = DraftRequest(
        project="proj",
        base_path=tmp_path,
        section=section,
        force_overwrite=False,
        project_id=1,
    )

    with pytest.raises(DraftOverwriteDenied):
        run_draft(
            request_obj,
            prompt=MagicMock(),
            repo=repo,
            finding_repo=MagicMock(),
            repo_repo=MagicMock(),
            event_sink=sink,
        )

    failed = next(e for e in captured_events if isinstance(e, DraftFailed))
    assert failed.error == "DraftOverwriteDenied"
    assert "already exists" in failed.message.lower()
