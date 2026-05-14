"""Coverage + cross-reference checks for the generated fixture tree.

Run after generate.py:
    python ui/tests/generator/check_coverage.py

Fails (non-zero exit) if:
- findings/populated.json is missing any canonical severity / status /
  segment value or any advertised tool.
- triage/reports/chat fixtures reference finding/scan ids that don't
  exist in the corresponding fixtures.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIX_ROOT = REPO_ROOT / "ui" / "testing" / "fixtures"

REQUIRED_SEVERITIES = {"critical", "high", "medium", "low", "informational"}
REQUIRED_STATUSES = {"active", "false_positive", "fixed", "wont_fix"}
REQUIRED_SEGMENTS = {"sast", "sca", "web", "secrets"}
REQUIRED_TOOLS = {
    "zap",
    "semgrep",
    "osv-scanner",
    "gitleaks",
    "pip-audit",
    "dalfox",
    "xsstrike",
}


def _load(rel: str) -> dict:
    return json.loads((FIX_ROOT / rel).read_text(encoding="utf-8"))


def check_findings_diversity() -> list[str]:
    """populated.json is the FIRST 50 findings. It may not cover every
    enum on its own. Source the diversity check from BOTH page-1 + page-2
    (which together cover the first 100), and counts-populated (which
    aggregates over the entire patched dataset)."""
    errors: list[str] = []
    populated = _load("findings/populated.json")
    page2 = _load("findings/page-2.json")
    counts = _load("findings/counts-populated.json")

    findings = populated["items"] + page2["items"]
    sev_in_findings = {f.get("severity") for f in findings}
    st_in_findings = {f.get("status") for f in findings}
    seg_in_findings = {f.get("segment") for f in findings}
    tool_in_findings = {f.get("tool") for f in findings}

    sev_in_counts = {k for k, v in counts["by_severity"].items() if v > 0}
    st_in_counts = {k for k, v in counts["by_status"].items() if v > 0}
    seg_in_counts = {k for k, v in counts["by_segment"].items() if v > 0}
    tool_in_counts = {k for k, v in counts["by_tool"].items() if v > 0}

    sev_total = sev_in_findings | sev_in_counts
    st_total = st_in_findings | st_in_counts
    seg_total = seg_in_findings | seg_in_counts
    tool_total = tool_in_findings | tool_in_counts

    missing = REQUIRED_SEVERITIES - sev_total
    if missing:
        errors.append(f"findings missing severities: {sorted(missing)}")
    missing = REQUIRED_STATUSES - st_total
    if missing:
        errors.append(f"findings missing statuses: {sorted(missing)}")
    missing = REQUIRED_SEGMENTS - seg_total
    if missing:
        errors.append(f"findings missing segments: {sorted(missing)}")
    missing = REQUIRED_TOOLS - tool_total
    if missing:
        errors.append(f"findings missing tools: {sorted(missing)}")

    return errors


def check_xrefs() -> list[str]:
    """triage detail and report fixtures should reference real ids."""
    errors: list[str] = []
    populated = _load("findings/populated.json")
    page2 = _load("findings/page-2.json")
    fid_pool = {int(f["id"]) for f in populated["items"]} | {
        int(f["id"]) for f in page2["items"]
    }
    scan_ids = {int(s["id"]) for s in _load("scans/history-project-1.json")["items"]}

    triage = _load("triage/detail-project-1.json")
    if triage["scan_run_id"] not in scan_ids:
        errors.append(
            f"triage/detail-project-1.json scan_run_id={triage['scan_run_id']} "
            f"not in scans/history-project-1.json scan ids"
        )
    for batch in triage["batches"]:
        for fid in batch["finding_ids"]:
            if int(fid) not in fid_pool:
                errors.append(
                    f"triage batch references finding_id={fid}, not in "
                    f"findings/populated.json+page-2.json"
                )

    reports_history = _load("reports/history-project-1.json")
    for r in reports_history["items"]:
        if r["scan_run_id"] is not None and int(r["scan_run_id"]) not in scan_ids:
            errors.append(
                f"reports history references scan_run_id={r['scan_run_id']}, "
                f"not in scans/history-project-1.json"
            )

    return errors


def main() -> int:
    print(f"Coverage check against {FIX_ROOT.relative_to(REPO_ROOT)}")
    errors: list[str] = []
    errors.extend(check_findings_diversity())
    errors.extend(check_xrefs())

    if errors:
        print("\nFAIL - coverage / cross-reference issues:")
        for e in errors:
            print(f"  ✗ {e}")
        return 1

    print(
        "OK - every required severity / status / segment / tool present, "
        "all id cross-references valid."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
