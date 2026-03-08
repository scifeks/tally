#!/usr/bin/env python3
"""Generate gitleaks fixture files from a real gitleaks run.

Run from the tally project root:
    python tests/ingest/tools/generate_gitleaks_fixtures.py

Requires: gitleaks in PATH, git in PATH

The generated fixtures are committed to the repository as ground truth for
what gitleaks actually emits.  Re-run this script when upgrading gitleaks
and review the diff before committing.

Design
------
A synthetic git repo is created in a temp directory containing a single file
``config/aws.js`` with nine leading blank lines so that the AWS key lands on
line 10.  This matches the hardcoded assertion in
``test_xfail_combine_dedup_dir_git_shared_finding``.

Two scans are performed:
  * dir scan  (--no-git) → gitleaks_dir.json  (commit field is empty string)
  * git scan  (default)  → gitleaks_git.json  (commit field is a real hash)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

FIXTURES = (
    Path(__file__).resolve().parents[2] / "fixtures" / "ingest"
)  # tests/fixtures/ingest/

# Nine leading blank lines place the AWS key at line 10, matching the
# hardcoded assertion in test_xfail_combine_dedup_dir_git_shared_finding.
#
# Key design: AKIA prefix + 16 chars from [A-Z2-7] triggers the gitleaks
# `aws-access-token` rule (regex: \b((?:AKIA|...)[A-Z2-7]{16})\b, entropy≥3).
# AKIAIOSFODNN7EXAMPLE is on gitleaks' allowlist and produces 0 findings.
_SECRET_FILE = "config/aws.js"
_SECRET_CONTENT = "\n" * 9 + 'const aws_key = "AKIAZ3XYMWQ2LR7NVBPA";\n'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _create_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _git(repo, "config", "user.email", "test@test.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "config").mkdir()
    (repo / _SECRET_FILE).write_text(_SECRET_CONTENT)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Add config with AWS credentials")
    return repo


def _run_gitleaks(repo: Path, *, no_git: bool, out: Path) -> int:
    # Run from within the repo directory with --source . so that the File
    # field in the output is a repo-relative path (e.g. "config/aws.js")
    # rather than an absolute path.
    args = [
        "gitleaks",
        "detect",
        "--source",
        ".",
        "--report-format",
        "json",
        "--report-path",
        str(out),
    ]
    if no_git:
        args.append("--no-git")
    result = subprocess.run(args, capture_output=True, cwd=str(repo))
    # exit 0 = no findings, exit 1 = findings found (both are expected outcomes)
    if result.returncode not in (0, 1):
        print(f"ERROR: {result.stderr.decode()}", file=sys.stderr)
        raise RuntimeError(f"gitleaks exited with code {result.returncode}")
    if out.exists():
        raw = json.loads(out.read_text())
        return len(raw) if isinstance(raw, list) else 0
    return 0


def _write_meta(fixture_path: Path, *, no_git: bool, version: str) -> None:
    flag = " --no-git" if no_git else ""
    meta = {
        "_generated_by": "tests/ingest/tools/generate_gitleaks_fixtures.py",
        "_gitleaks_version": version,
        "_generated_at": datetime.now(UTC).isoformat(),
        "_scan_mode": "dir (--no-git)" if no_git else "git",
        "_command": f"gitleaks detect --source <repo> --report-format json{flag}",
        "_secret_file": _SECRET_FILE,
        "_secret_description": "AKIAZ3XYMWQ2LR7NVBPA at line 10",
    }
    meta_path = fixture_path.parent / (fixture_path.stem + ".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(f"  Wrote {meta_path.name}")


def _get_version() -> str:
    result = subprocess.run(["gitleaks", "version"], capture_output=True, text=True)
    return (result.stdout or result.stderr).strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    version = _get_version()
    print(f"gitleaks {version}")

    with tempfile.TemporaryDirectory() as tmp:
        repo = _create_repo(Path(tmp))
        print(f"Created synthetic repo at {repo}")

        dir_out = FIXTURES / "gitleaks_dir.json"
        git_out = FIXTURES / "gitleaks_git.json"

        print("Running dir scan (--no-git) ...")
        n_dir = _run_gitleaks(repo, no_git=True, out=dir_out)
        print(f"  {n_dir} finding(s) → {dir_out.name}")
        _write_meta(dir_out, no_git=True, version=version)

        print("Running git scan ...")
        n_git = _run_gitleaks(repo, no_git=False, out=git_out)
        print(f"  {n_git} finding(s) → {git_out.name}")
        _write_meta(git_out, no_git=False, version=version)

    print("\nDone.  Review and commit the updated fixtures:")
    print("  git diff --stat tests/fixtures/ingest/")
    print("  git add tests/fixtures/ingest/")


if __name__ == "__main__":
    main()
