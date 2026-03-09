#!/usr/bin/env python3
"""
Inspect gitleaks output files and report what the app actually sees
after parsing and deduplication.

Usage:
    python3 inspect_gitleaks.py
"""

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paste of parser logic from core/parsers/gitleaks.py
# (copied verbatim so this script is self-contained)
# ---------------------------------------------------------------------------


def _redact_secret(secret: str) -> str:
    if not secret:
        return "****"
    if len(secret) < 10:
        return "****"
    return secret[:4] + "****"


def _parse_secret(finding: dict) -> dict:
    raw_secret = finding.get("Secret", "")
    tags = finding.get("Tags") or []
    commit = finding.get("Commit") or None
    return {
        "rule_id": finding.get("RuleID", ""),
        "description": finding.get("Description", ""),
        "file_path": finding.get("File", ""),
        "line_number": finding.get("StartLine", 0),
        "commit": commit,
        "secret": _redact_secret(raw_secret),
        "match": finding.get("Match", ""),
        "tags": tags,
        "fingerprint": finding.get("Fingerprint", ""),
    }


def _parse_gitleaks_data(findings) -> dict:
    if findings is None:
        findings = []
    if not isinstance(findings, list):
        return {"error": "Unexpected gitleaks output format (expected JSON array)"}
    secrets = [_parse_secret(f) for f in findings]
    by_rule: dict[str, int] = {}
    files_with_secrets: set[str] = set()
    for secret in secrets:
        rule = secret["rule_id"]
        by_rule[rule] = by_rule.get(rule, 0) + 1
        if secret["file_path"]:
            files_with_secrets.add(secret["file_path"])
    return {
        "secrets": secrets,
        "summary": {
            "total_secrets": len(secrets),
            "by_rule": by_rule,
            "files_with_secrets": len(files_with_secrets),
        },
    }


def parse_gitleaks_json(json_path: Path) -> dict:
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_gitleaks_data(data)


def combine_gitleaks_results(dir_data: dict, git_data: dict) -> dict:
    dir_secrets = (dir_data or {}).get("secrets", [])
    git_secrets = (git_data or {}).get("secrets", [])

    seen: set[tuple] = set()
    merged: list[dict] = []
    for secret in dir_secrets + git_secrets:
        key = (
            secret.get("rule_id", ""),
            secret.get("file_path", ""),
            secret.get("line_number", 0),
        )
        if key not in seen:
            seen.add(key)
            merged.append(secret)

    by_rule: dict[str, int] = {}
    files_with_secrets: set[str] = set()
    for secret in merged:
        rule = secret.get("rule_id", "")
        by_rule[rule] = by_rule.get(rule, 0) + 1
        if secret.get("file_path"):
            files_with_secrets.add(secret["file_path"])

    return {
        "dir": dir_data,
        "git": git_data,
        "secrets": merged,
        "summary": {
            "total_secrets": len(merged),
            "by_rule": by_rule,
            "files_with_secrets": len(files_with_secrets),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DIR_FILE = Path("/tmp/gitleaks_dir.json")
GIT_FILE = Path("/tmp/gitleaks_git.json")


def load_file(path: Path) -> dict:
    if not path.exists():
        print(f"  WARNING: {path} does not exist — skipping")
        return {}
    print(f"  Loading {path} ({path.stat().st_size:,} bytes)")
    return parse_gitleaks_json(path)


def main():
    print("=" * 70)
    print("GITLEAKS OUTPUT INSPECTION")
    print("=" * 70)

    print("\n--- Loading files ---")
    dir_data = load_file(DIR_FILE)
    git_data = load_file(GIT_FILE)

    if "error" in dir_data:
        print(f"  ERROR in dir file: {dir_data['error']}")
    if "error" in git_data:
        print(f"  ERROR in git file: {git_data['error']}")

    dir_count = len((dir_data or {}).get("secrets", []))
    git_count = len((git_data or {}).get("secrets", []))
    print(f"\n  dir scan raw findings : {dir_count}")
    print(f"  git scan raw findings : {git_count}")
    print(f"  total before dedupe   : {dir_count + git_count}")

    print("\n--- Deduplication ---")
    combined = combine_gitleaks_results(dir_data, git_data)
    merged = combined.get("secrets", [])
    dupes_removed = (dir_count + git_count) - len(merged)
    print(f"  total after dedupe    : {len(merged)}")
    print(f"  duplicates removed    : {dupes_removed}")

    print("\n--- By rule ---")
    by_rule = combined["summary"]["by_rule"]
    for rule, count in sorted(by_rule.items(), key=lambda x: -x[1]):
        print(f"  {count:4d}  {rule}")

    print(f"\n--- Files with secrets: {combined['summary']['files_with_secrets']} ---")

    print("\n--- All findings (what the app sees after dedupe) ---")
    print(f"  {'#':<5} {'rule_id':<30} {'file_path':<60} {'line':>5}  secret")
    print(f"  {'-' * 5} {'-' * 30} {'-' * 60} {'-' * 5}  {'-' * 10}")
    for i, s in enumerate(merged, 1):
        file_path = s.get("file_path", "")
        # Truncate long paths from the left so the filename is always visible
        if len(file_path) > 60:
            file_path = "..." + file_path[-57:]
        print(
            f"  {i:<5} "
            f"{s.get('rule_id', ''):<30} "
            f"{file_path:<60} "
            f"{s.get('line_number', 0):>5}  "
            f"{s.get('secret', '')}"
        )

    print(f"\n  Total: {len(merged)} findings")
    print("=" * 70)


if __name__ == "__main__":
    main()
