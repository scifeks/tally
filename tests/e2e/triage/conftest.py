"""E2E triage configuration.

Provides environment detection helpers, finding templates, and a
triage_env fixture that seeds SAST and web findings and starts real
triage containers. Also manages ChromaDB cleanup for the e2e suite.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from chromadb.api.shared_system_client import SharedSystemClient

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.compose import (  # noqa: E402
    COMPOSE_RELATIVE_PATH,
    generate_triage_compose,
)
from application.triage.container import TRIAGE_IMAGE_TAG  # noqa: E402
from infrastructure.docker.triage_container import (  # noqa: E402
    DockerTriageContainer,
)
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.connection import (  # noqa: E402
    ConnectionFactory,
)
from tests.finding_helpers import normalize_test_findings  # noqa: E402

pytestmark = pytest.mark.e2e


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

_SAST_FINDING_TEMPLATE: dict[str, Any] = {
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

_WEB_FINDING_TEMPLATE: dict[str, Any] = {
    "tool": "graphql-cop",
    "domain": "web",
    "segment": "web",
    "finding_type": "exposure",
    "severity": "medium",
    "confidence": "potential",
    "url": "http://localhost:8000/graphql",
    "description": "GraphQL schema introspection enabled",
    "risk_type": "information_disclosure",
    "alert_name": "GraphQL Schema Introspection",
    "method": "POST",
}


# -- fixtures ------------------------------------------------------------


@pytest.fixture()
def triage_env(tmp_path: Path):
    """Set up a complete triage environment with real containers.

    Seeds both SAST and web findings, generates compose, starts
    containers. Skips if preconditions are not met. Tears down
    containers on exit regardless of test outcome.
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

    project = "e2e_triage"
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

    sast_finding = {**_SAST_FINDING_TEMPLATE, "repo_id": repo_id}
    web_finding = {**_WEB_FINDING_TEMPLATE, "repo_id": repo_id}
    finding_repo.insert_findings(
        run_id,
        normalize_test_findings([sast_finding, web_finding]),
    )

    with factory.connect() as conn:
        rows = conn.execute("SELECT id, segment FROM findings ORDER BY id").fetchall()

    finding_ids = {row["segment"]: row["id"] for row in rows}

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
        "finding_ids": finding_ids,
        "repo_paths": repo_paths,
    }

    try:
        container_port.down(compose_path)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _cleanup_chromadb_systems():
    """Stop and evict every ChromaDB System created during this test."""
    yield
    for system in list(SharedSystemClient._identifier_to_system.values()):
        try:
            system.stop()
        except Exception:
            pass
    SharedSystemClient._identifier_to_system.clear()
    SharedSystemClient._identifier_to_refcount.clear()
