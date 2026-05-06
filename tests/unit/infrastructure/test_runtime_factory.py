"""Tests runtime probe selection."""

from __future__ import annotations

import json
from pathlib import Path

from infrastructure.runtime.factory import build_runtime_dependency_probes


def _write_global_config(base_path: Path, payload: dict) -> None:
    cfg_dir = base_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "global.json").write_text(json.dumps(payload))


def test_build_runtime_dependency_probes_uses_claude_probe_when_configured(
    tmp_path: Path,
) -> None:
    _write_global_config(tmp_path, {"triage_agent_provider": "claude_code"})

    probes = build_runtime_dependency_probes(base_path=tmp_path)

    assert [probe.requirement.name for probe in probes] == ["claude"]


def test_build_runtime_dependency_probes_skips_probes_when_triage_disabled(
    tmp_path: Path,
) -> None:
    _write_global_config(tmp_path, {"triage_agent_provider": ""})

    assert build_runtime_dependency_probes(base_path=tmp_path) == []


def test_build_runtime_dependency_probes_skips_open_code_until_supported(
    tmp_path: Path,
) -> None:
    _write_global_config(tmp_path, {"triage_agent_provider": "open_code"})

    probes = build_runtime_dependency_probes(base_path=tmp_path)

    assert [probe.requirement.name for probe in probes] == ["opencode"]
