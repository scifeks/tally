"""Tests triage composition."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.factory import (
    ResolvedTriageConfig,
    TriageProviderNotConfiguredError,
    build_triage_runner,
    ensure_triage_backend_configured,
    load_triage_provider,
    resolve_triage_config,
)


def _resolved(
    provider: str = "ollama",
    base_url: str = "http://localhost:11434",
    model: str = "testmodel",
    timeout: int = 300,
    retry_count: int = 0,
    debug: bool = False,
) -> ResolvedTriageConfig:
    return ResolvedTriageConfig(
        provider_name=provider,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout,
        retry_count=retry_count,
        debug=debug,
    )


def test_load_triage_provider_reads_triage_inference(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "m",
                },
                "triage_inference": {"provider": "ollama"},
            }
        )
    )

    assert load_triage_provider(app_root=tmp_path) == "ollama"


def test_load_triage_provider_falls_back_to_legacy(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(
        json.dumps({"triage_agent_provider": "claude_code"})
    )

    assert load_triage_provider(app_root=tmp_path) == "claude_code"


def test_ensure_triage_backend_configured_raises_when_disabled(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(json.dumps({}))

    with pytest.raises(
        TriageProviderNotConfiguredError,
        match="Triage is disabled",
    ):
        ensure_triage_backend_configured(app_root=tmp_path)


def test_resolve_triage_config_merges_overrides(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://host:11434",
                    "model": "default-model",
                    "timeout_seconds": 60,
                },
                "triage_inference": {
                    "provider": "ollama",
                    "model": "override-model",
                    "timeout_seconds": 180,
                },
            }
        )
    )

    resolved = resolve_triage_config(app_root=tmp_path)
    assert resolved.provider_name == "ollama"
    assert resolved.base_url == "http://host:11434"
    assert resolved.model == "override-model"
    assert resolved.timeout_seconds == 180


def test_resolve_triage_config_merges_retry_count(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://host:11434",
                    "model": "m",
                },
                "triage_inference": {
                    "provider": "ollama",
                    "retry_count": 3,
                },
            }
        )
    )

    resolved = resolve_triage_config(app_root=tmp_path)
    assert resolved.retry_count == 3


def test_resolve_triage_config_defaults_retry_count(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://host:11434",
                    "model": "m",
                },
                "triage_inference": {
                    "provider": "ollama",
                },
            }
        )
    )

    resolved = resolve_triage_config(app_root=tmp_path)
    assert resolved.retry_count == 0


def test_resolve_triage_config_uses_provider_defaults(
    tmp_path: Path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "llama_cpp": {
                    "base_url": "http://host:8080",
                    "model": "qwen3:14b",
                    "timeout_seconds": 90,
                },
                "triage_inference": {
                    "provider": "llama_cpp",
                },
            }
        )
    )

    resolved = resolve_triage_config(app_root=tmp_path)
    assert resolved.provider_name == "llama_cpp"
    assert resolved.base_url == "http://host:8080"
    assert resolved.model == "qwen3:14b"
    assert resolved.timeout_seconds == 90


def test_build_triage_runner_uses_factory_agent(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True)
    findings_db.touch()

    tool_registry = MagicMock()
    run_repo, finding_repo, triage_repo, audit_repo = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    with (
        patch("application.triage.factory.TriageAgentFactory"),
        patch(
            "application.triage.factory.resolve_triage_config",
            return_value=_resolved(provider="ollama"),
        ),
    ):
        runner = build_triage_runner(
            "proj",
            tool_registry,
            app_root=tmp_path,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
        )

    assert runner is not None


def test_build_triage_runner_claude_triaged_by(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True)
    findings_db.touch()

    run_repo, finding_repo, triage_repo, audit_repo = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    with (
        patch("application.triage.factory.TriageAgentFactory"),
        patch(
            "application.triage.factory.resolve_triage_config",
            return_value=_resolved(provider="claude"),
        ),
    ):
        runner = build_triage_runner(
            "proj",
            MagicMock(),
            app_root=tmp_path,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
        )

    assert runner._triaged_by == "claudecode"


def test_build_triage_runner_wires_finding_repo(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True)
    findings_db.touch()

    run_repo = MagicMock()
    finding_repo = MagicMock()
    triage_repo = MagicMock()
    audit_repo = MagicMock()

    with (
        patch("application.triage.factory.TriageAgentFactory"),
        patch(
            "application.triage.factory.resolve_triage_config",
            return_value=_resolved(),
        ),
    ):
        runner = build_triage_runner(
            "proj",
            MagicMock(),
            app_root=tmp_path,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
        )

    assert runner is not None


def test_build_triage_runner_resets_for_resume(
    tmp_path: Path,
) -> None:
    findings_db = tmp_path / "projects" / "proj" / "sqlite" / "findings.db"
    findings_db.parent.mkdir(parents=True)
    findings_db.touch()

    run_repo = MagicMock()
    finding_repo = MagicMock()
    triage_repo = MagicMock()
    audit_repo = MagicMock()

    with (
        patch("application.triage.factory.TriageAgentFactory"),
        patch(
            "application.triage.factory.resolve_triage_config",
            return_value=_resolved(),
        ),
    ):
        build_triage_runner(
            "proj",
            MagicMock(),
            app_root=tmp_path,
            run_repo=run_repo,
            finding_repo=finding_repo,
            triage_repo=triage_repo,
            audit_repo=audit_repo,
            repo_paths={},
            reset_for_resume_scan_run_id=17,
        )

    triage_repo.reset_for_resume.assert_called_once_with(17)


def test_build_triage_runner_raises_when_project_db_missing(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="Project database not found"):
        build_triage_runner(
            "proj",
            MagicMock(),
            app_root=tmp_path,
            run_repo=MagicMock(),
            finding_repo=MagicMock(),
            triage_repo=MagicMock(),
            audit_repo=MagicMock(),
            repo_paths={},
        )
