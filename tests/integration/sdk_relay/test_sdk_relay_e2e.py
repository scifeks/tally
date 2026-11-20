"""End-to-end test of the sdk-runner inside the real triage-agent image.

Skipped unless DOCKER=1 and a docker binary is on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

requires_docker = pytest.mark.skipif(
    os.environ.get("DOCKER") != "1" or shutil.which("docker") is None,
    reason="requires DOCKER=1 and docker on PATH",
)

_IMAGE = "tally-triage-agent:test"
_JOB_SPEC = (
    '{"mode":"triage","model":"opus","system_prompt":"",'
    '"user_prompt":"","allowed_tools":[],"cwd":"/workspace",'
    '"timeout_seconds":30}\n'
)


@requires_docker
@pytest.mark.requires_docker
def test_relay_roundtrip() -> None:
    image_dir = Path(__file__).resolve().parents[3] / "docker" / "triage-agent"
    subprocess.run(["docker", "build", "-t", _IMAGE, str(image_dir)], check=True)

    # The fake response bypasses claude_agent_sdk so no API key is needed.
    env = os.environ.copy()
    env["SDK_RUNNER_FAKE_RESPONSE"] = '{"finding_id":1,"confidence":"confirmed"}'

    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-e",
            "SDK_RUNNER_FAKE_RESPONSE",
            _IMAGE,
            "sdk-runner",
        ],
        input=_JOB_SPEC,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert any('"type": "result"' in line for line in lines)
    assert any('"type": "end"' in line for line in lines)
