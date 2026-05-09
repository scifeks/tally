"""Integration smoke test: real Docker container, real OpenCode agent.

Exercises the full triage path against a single SAST finding:
seed finding in SQLite, generate compose, start containers, invoke
the agent inside the container via docker compose exec, and verify
the verdict is persisted back to the database.

Skipped automatically when Docker, the triage image, or Ollama
is unavailable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.compose import (  # noqa: E402
    COMPOSE_RELATIVE_PATH,
    generate_triage_compose,
)
from application.triage.container import TRIAGE_IMAGE_TAG  # noqa: E402
from application.triage.factory import (  # noqa: E402
    TriageAgentFactory,
)
from application.triage.runner import TriageRunner  # noqa: E402
from domain.tools.constants import CONFIDENCE_LEVELS  # noqa: E402
from infrastructure.docker.triage_container import (  # noqa: E402
    DockerTriageContainer,
)
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from tests.conftest import requires_docker  # noqa: E402

pytestmark = pytest.mark.integration


# -- skip helpers --------------------------------------------------------


def _triage_image_exists() -> bool:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", TRIAGE_IMAGE_TAG],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _ollama_available() -> tuple[bool, str]:
    """Returns (available, base_url).

    Reads config/global.json directly to avoid schema validation
    failures when the real config has field values that the current
    Pydantic schema hasn't been updated to accept yet.
    """
    try:
        from infrastructure.llm.ollama_utils import (
            verify_ollama_available,
        )

        cfg_path = _TALLY_ROOT / "config" / "global.json"
        if not cfg_path.exists():
            return False, ""
        data = json.loads(cfg_path.read_text())
        ollama = data.get("ollama")
        if not isinstance(ollama, dict):
            return False, ""
        url = ollama.get("base_url", "")
        if not url:
            return False, ""
        if not verify_ollama_available(url):
            return False, ""
        return True, url
    except Exception:
        return False, ""


_MIN_MODEL_BYTES = 8_000_000_000


def _smallest_ollama_model(url: str) -> str | None:
    """Returns the smallest general-purpose Ollama model.

    Filters out embedding models and models under 8 GB (fine-tuned
    small models tend not to follow structured output schemas).
    """
    import urllib.request

    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
        models = data.get("models", [])
        _EXCLUDE = ("embed", "bge-", "nomic")
        candidates = [
            m
            for m in models
            if not any(e in m.get("name", "") for e in _EXCLUDE)
            and m.get("size", 0) >= _MIN_MODEL_BYTES
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda m: m.get("size", 0))
        return candidates[0].get("name", "")
    except Exception:
        pass
    return None


def _detect_opencode_backend() -> tuple[dict[str, Any], str, str] | None:
    """Build a config dict using the triage_inference pattern.

    Returns (config_dict, ollama_url, model) or None.
    """
    available, ollama_url = _ollama_available()
    if not available:
        return None
    model = _smallest_ollama_model(ollama_url)
    if not model:
        return None
    return (
        {
            "ollama": {
                "base_url": ollama_url,
                "model": model,
            },
            "triage_inference": {
                "provider": "ollama",
                "model": model,
            },
        },
        ollama_url,
        model,
    )


# -- fixture data --------------------------------------------------------

_VULNERABLE_SOURCE = """\
import sqlite3


def get_user(db_path, user_input):
    conn = sqlite3.connect(db_path)
    query = "SELECT * FROM users WHERE name = '" + user_input + "'"
    return conn.execute(query).fetchall()
"""

_FINDING_TEMPLATE: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "potential",
    "file_path": "src/app.py",
    "rule_id": "python.lang.security.audit.sqli.string-concat-query",
    "description": "String concatenation in SQL query",
    "cwe": ["CWE-89"],
    "line_start": 6,
    "code_snippet": (
        'query = "SELECT * FROM users WHERE name = \'" + user_input + "\'"'
    ),
    "risk_type": "SQL Injection",
    "owasp": "A03:2021-Injection",
}


# -- fixtures ------------------------------------------------------------


@pytest.fixture()
def triage_env(tmp_path: Path):
    """Set up a complete triage environment with real containers.

    Skips if preconditions are not met. Tears down containers
    on exit regardless of test outcome.
    """
    if not _triage_image_exists():
        pytest.skip(f"{TRIAGE_IMAGE_TAG} image not built")

    detected = _detect_opencode_backend()
    if detected is None:
        pytest.skip("Ollama not available for OpenCode backend")
    config_dict, ollama_url, model = detected

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "global.json").write_text(json.dumps(config_dict))

    repo_dir = tmp_path / "repos" / "testrepo"
    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "app.py").write_text(_VULNERABLE_SOURCE)

    project = "smoketest"
    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_path, project)
    db_path = tmp_path / "projects" / project / "sqlite" / "findings.db"
    factory = ConnectionFactory(db_path)

    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name, path) VALUES (?, ?)",
            ("testrepo", str(repo_dir)),
        )
        repo_id = cur.lastrowid

    run_id = run_repo.create_run({})
    finding = {**_FINDING_TEMPLATE, "repo_id": repo_id}
    finding_repo.insert_findings(run_id, [finding])

    with factory.connect() as conn:
        row = conn.execute("SELECT id FROM findings ORDER BY id LIMIT 1").fetchone()
    finding_id = row["id"]

    repo_paths: dict[str, Path] = {"testrepo": repo_dir}
    compose_path = tmp_path / COMPOSE_RELATIVE_PATH
    generate_triage_compose(
        tmp_path,
        repo_paths,
        provider="ollama",
        base_url=ollama_url,
        model=model,
    )

    container_port = DockerTriageContainer()
    container_port.up(compose_path)

    yield {
        "tmp_path": tmp_path,
        "project": project,
        "compose_path": compose_path,
        "run_repo": run_repo,
        "finding_repo": finding_repo,
        "triage_repo": triage_repo,
        "factory": factory,
        "finding_id": finding_id,
        "repo_paths": repo_paths,
    }

    try:
        container_port.down(compose_path)
    except Exception:
        pass


# -- test ----------------------------------------------------------------


@requires_docker
@pytest.mark.timeout(300)
def test_single_finding_triaged_via_container(
    triage_env: dict[str, Any],
) -> None:
    env = triage_env
    tmp_path: Path = env["tmp_path"]

    tool_mock = MagicMock()
    tool_mock.name = "semgrep"
    tool_mock.skip = False
    tool_mock.scan_segment = "sast"
    registry = MagicMock()
    registry.get_all_tools.return_value = []
    registry.get_tool.return_value = tool_mock

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
        triaged_by="opencode",
    )

    result = runner.run()
    assert result.success >= 1

    finding_id = env["finding_id"]
    factory: ConnectionFactory = env["factory"]
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT enriched, triaged_at, triaged_by,"
            " confidence, meta"
            " FROM findings WHERE id = ?",
            (finding_id,),
        ).fetchone()

    assert row is not None, f"finding {finding_id} not in DB"
    assert row["enriched"] == 1
    assert row["triaged_at"] is not None
    assert row["triaged_by"] == "opencode"
    assert row["confidence"] in CONFIDENCE_LEVELS

    meta = json.loads(row["meta"] or "{}")
    triage_meta = meta.get("triage", {})
    assert triage_meta.get("reasoning"), "reasoning is empty"
    assert triage_meta.get("remediation"), "remediation is empty"
