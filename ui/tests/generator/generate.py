"""Generate UI test fixtures in ui/tests/fixtures/ from real DB data.

Run from the repo root:
    python ui/tests/generator/generate.py

Read-only with respect to all SQLite databases and the project JSON.
Writes only to ui/tests/fixtures/.
"""

from __future__ import annotations

import copy
import json
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Make repo top-level packages importable when invoked as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from domain.findings.entry import Finding  # noqa: E402
from web.api.findings import _serialise_finding  # noqa: E402
from web.api.schemas import (  # noqa: E402
    ChatMessageSendResponse,
    ChatMessagesListResponse,
    ChatSessionsListResponse,
    ChatSessionSummary,
    FindingsCountsResponse,
    FindingsFilterOptionsResponse,
    FindingsListResponse,
    ProjectInfoResponse,
    ProjectListResponse,
    ProjectMetaResponse,
    ReportsListResponse,
    ReportSummary,
    ScanCancelResponse,
    ScanConfigResponse,
    ScanRunSummary,
    ScansListResponse,
    ToolCatalogResponse,
    TriageCancelResponse,
    TriageDetailResponse,
    TriageRunSummary,
    TriagesListResponse,
    UrlListFilterOptionsResponse,
)
from web.api.tool_overrides_schemas import (  # noqa: E402
    ToolOverrideListResponse,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

THIS_DIR = Path(__file__).resolve().parent
SEEDS_DIR = THIS_DIR / "seeds"
TALLY_DB = _REPO_ROOT / "tally.db"
DVPA_DB = _REPO_ROOT / "projects" / "DVPA" / "sqlite" / "findings.db"
DVPA_PROJECT_JSON = _REPO_ROOT / "projects" / "DVPA" / "config" / "project.json"
OUTPUT_DIR = _REPO_ROOT / "ui" / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _strip_comments(obj: Any) -> Any:
    """Recursively drop keys starting with '_' (used for inline _comment)."""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


def _open_ro(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite DB strictly read-only via URI mode."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _write_fixture(rel_path: str, data: Any) -> None:
    out = OUTPUT_DIR / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {out.relative_to(_REPO_ROOT)}")


def _validate(model: type, payload: Any) -> None:
    """Pydantic model_validate. Raises if the payload drifts from schema."""
    model.model_validate(payload)


_REPO_JSON_COLS = (
    "type",
    "languages",
    "base_urls",
    "test_dirs",
    "ignore_dirs",
    "xsstrike_headers",
    "dalfox_headers",
    "katana_headers",
    "auth",
)


def _repo_row_to_dict(row: dict) -> dict:
    """Hydrate a ``repositories`` SQLite row into a Repository-shaped dict.

    JSON columns (``*_json``) are decoded; auth ``null`` becomes ``None``;
    integer flags are coerced to ``bool``. ``url_seed_file`` is preserved
    so the response serialiser can derive ``endpoint_file``.
    """
    out: dict = {
        "id": int(row["id"]),
        "name": row["name"],
        "path": row.get("path", "") or "",
        "docker_path": row.get("docker_path", "") or "",
        "container_name": row.get("container_name", "") or "",
        "dependencies_file": row.get("dependencies_file", "") or "",
        "crawl_enabled": bool(row.get("crawl_enabled", 1)),
        "xsstrike_crawl_level": int(row.get("xsstrike_crawl_level", 10)),
        "katana_headless": bool(row.get("katana_headless", 0)),
        "katana_depth": int(row.get("katana_depth", 5)),
        "url_seed_file": row.get("url_seed_file"),
    }
    for key in _REPO_JSON_COLS:
        raw = row.get(f"{key}_json")
        if raw is None or raw == "":
            out[key] = None if key == "auth" else []
        else:
            out[key] = json.loads(raw)
    return out


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def _derive_code(name: str) -> str:
    """Derive a project 'code' from name when none is registered."""
    letters = [c for c in name.upper() if c.isalpha()]
    return "".join(letters[:3]) if letters else name[:3].upper()


def build_context() -> dict[str, Any]:
    """Build the context dict used by every domain producer."""
    print("Loading project registry from tally.db...")
    with _open_ro(TALLY_DB) as t_conn:
        projects_rows = list(
            t_conn.execute(
                "SELECT id, name, path, created_at "
                "FROM projects WHERE archived_at IS NULL ORDER BY id"
            )
        )
    projects = [dict(r) for r in projects_rows]
    if not projects:
        raise RuntimeError("tally.db has no active projects")
    project_1 = projects[0]
    if len(projects) >= 2:
        project_2 = projects[1]
    else:
        # Only one real project, so synthesize a project-2 placeholder so the
        # second-tenant fixtures still render. Distinct id avoids cross-fixture
        # collisions; payload otherwise mirrors project-1.
        project_2 = {
            **project_1,
            "id": int(project_1["id"]) + 1,
            "name": f"{project_1['name']}-alt",
        }
        projects.append(project_2)

    print("Loading DVPA project.json...")
    dvpa_project = _read_json(DVPA_PROJECT_JSON)

    print("Loading DVPA findings.db rows (read-only)...")
    with _open_ro(DVPA_DB) as f_conn:
        finding_rows = [dict(r) for r in f_conn.execute("SELECT * FROM findings")]
        url_rows = [dict(r) for r in f_conn.execute("SELECT * FROM url_findings")]
        repo_rows = [dict(r) for r in f_conn.execute("SELECT * FROM repositories")]
        scan_run_rows = [dict(r) for r in f_conn.execute("SELECT * FROM scan_runs")]
        run_tool_rows = [dict(r) for r in f_conn.execute("SELECT * FROM run_tools")]

    print(
        f"  findings={len(finding_rows)}, url_findings={len(url_rows)}, "
        f"repos={len(repo_rows)}, scan_runs={len(scan_run_rows)}, "
        f"run_tools={len(run_tool_rows)}"
    )

    real_scan_run = scan_run_rows[0] if scan_run_rows else None
    if real_scan_run is None:
        raise RuntimeError("DVPA findings.db has no scan_runs rows")

    return {
        "projects": projects,
        "project_1": project_1,
        "project_2": project_2,
        "project_1_id": int(project_1["id"]),
        "project_2_id": int(project_2["id"]),
        "project_1_name": project_1["name"],
        "project_2_name": project_2["name"],
        "project_1_code": _derive_code(project_1["name"]),
        "project_2_code": _derive_code(project_2["name"]),
        "dvpa_project": dvpa_project,
        "finding_rows": finding_rows,
        "url_rows": url_rows,
        "repo_rows": repo_rows,
        "scan_run": real_scan_run,
        "tool_runs": run_tool_rows,
    }


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def _next_finding_id(rows: Iterable[dict]) -> int:
    """Return the next free finding id (1 + max existing id)."""
    return 1 + max((int(r["id"]) for r in rows), default=0)


def _apply_diversity_overrides(rows: list[dict], overrides: dict) -> None:
    """Mutate rows in place per overrides manifest. Deterministic by tool+nth."""
    by_tool: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda x: int(x["id"])):
        by_tool[r["tool"]].append(r)

    triaged_at = overrides["triaged_timestamp"]
    triaged_by = overrides["triaged_by"]

    for promo in overrides.get("severity_promotions_to_critical", []):
        bucket = by_tool.get(promo["tool"], [])
        idx = promo["nth"]
        if idx < len(bucket):
            # Severity ranks are inverted: rank 0 = critical, rank 4 = info.
            bucket[idx]["severity"] = 0

    for ov in overrides.get("status_overrides", []):
        bucket = by_tool.get(ov["tool"], [])
        idx = ov["nth"]
        if idx < len(bucket):
            row = bucket[idx]
            row["status"] = ov["status"]
            if ov["status"] != "active":
                row["triaged_at"] = triaged_at
                row["triaged_by"] = triaged_by


def _build_findings_list(ctx: dict) -> list[dict]:
    """Return the patched + appended-with-seeds list of DB-row-shape findings."""
    rows = [copy.deepcopy(r) for r in ctx["finding_rows"]]

    # Append dalfox + xsstrike seeds with fresh ids.
    next_id = _next_finding_id(rows)
    for path in ("findings/dalfox.json", "findings/xsstrike.json"):
        seed_rows = _read_json(SEEDS_DIR / path)
        for seed in seed_rows:
            row = dict(seed)
            row["id"] = next_id
            next_id += 1
            # finding_type and cwe must be JSON-string in DB-row shape; the
            # seeds carry them as Python lists for readability, so encode now.
            if isinstance(row.get("finding_type"), list):
                row["finding_type"] = json.dumps(row["finding_type"])
            if isinstance(row.get("cwe"), list):
                row["cwe"] = json.dumps(row["cwe"])
            if isinstance(row.get("meta"), dict):
                row["meta"] = json.dumps(row["meta"])
            rows.append(row)

    # Apply diversity overrides at the input layer.
    overrides = _read_json(SEEDS_DIR / "findings/diversity_overrides.json")
    _apply_diversity_overrides(rows, overrides)

    return rows


def _serialise_findings(rows: list[dict], project_id: int) -> list[dict]:
    """Run the production serializer over rows and inject project_id."""
    out: list[dict] = []
    for row in rows:
        serial = _serialise_finding(Finding.from_row(row), (False, None))
        serial["project_id"] = project_id
        out.append(serial)
    return out


SEVERITY_LABELS = ["informational", "low", "medium", "high", "critical"]


def _compute_counts(serialised: list[dict]) -> dict[str, Any]:
    """Compute FindingsCountsResponse-shape aggregates from serialised data."""
    by_severity: dict[str, int] = {lbl: 0 for lbl in SEVERITY_LABELS}
    by_status: dict[str, int] = {
        "active": 0,
        "false_positive": 0,
        "fixed": 0,
        "wont_fix": 0,
    }
    by_domain: dict[str, int] = {}
    by_segment: dict[str, int] = {}
    by_tool: dict[str, int] = {}
    by_repo: dict[str, int] = {}
    by_severity_status: dict[str, dict[str, int]] = {
        sev: {st: 0 for st in by_status} for sev in SEVERITY_LABELS
    }

    last_triage_at: str | None = None
    repo_ids: set[int] = set()
    run_ids: set[int] = set()

    for f in serialised:
        sev = f.get("severity")
        if sev in by_severity:
            by_severity[sev] += 1
        st = f.get("status")
        if st in by_status:
            by_status[st] += 1
        if sev in by_severity_status and st in by_severity_status[sev]:
            by_severity_status[sev][st] += 1
        if d := f.get("domain"):
            by_domain[d] = by_domain.get(d, 0) + 1
        if s := f.get("segment"):
            by_segment[s] = by_segment.get(s, 0) + 1
        if t := f.get("tool"):
            by_tool[t] = by_tool.get(t, 0) + 1
        rid = f.get("repo_id")
        if rid is not None:
            repo_ids.add(int(rid))
        run_id = f.get("run_id")
        if run_id is not None:
            run_ids.add(int(run_id))
        ta = f.get("triaged_at")
        if ta and (last_triage_at is None or ta > last_triage_at):
            last_triage_at = ta

    return {
        "by_severity": by_severity,
        "by_domain": by_domain,
        "by_segment": by_segment,
        "by_repo": by_repo,
        "by_status": by_status,
        "by_tool": by_tool,
        "by_severity_status": by_severity_status,
        "total": len(serialised),
        "scans_count": len(run_ids),
        "repos_count": len(repo_ids),
        "urls_count": 0,
        "last_scan_at": None,
        "last_triage_at": last_triage_at,
    }


def produce_findings(ctx: dict) -> dict[str, Any]:
    """Emit findings/* fixtures. Returns metadata used by other producers."""
    print("Producing findings/...")
    rows = _build_findings_list(ctx)
    serialised_p1 = _serialise_findings(rows, ctx["project_1_id"])
    serialised_p2 = _serialise_findings(rows, ctx["project_2_id"])

    # findings/populated.json: first 50 of project-1
    populated = {
        "items": serialised_p1[:50],
        "total": len(serialised_p1),
        "offset": 0,
        "limit": 50,
    }
    _validate(FindingsListResponse, populated)
    _write_fixture("findings/populated.json", populated)

    # findings/page-2.json: next slice (offset=50)
    page2_items = serialised_p1[50:100]
    page2 = {
        "items": page2_items,
        "total": len(serialised_p1),
        "offset": 50,
        "limit": 50,
    }
    _validate(FindingsListResponse, page2)
    _write_fixture("findings/page-2.json", page2)

    # findings/empty.json
    empty = {"items": [], "total": 0, "offset": 0, "limit": 50}
    _validate(FindingsListResponse, empty)
    _write_fixture("findings/empty.json", empty)

    # findings/counts-populated.json: derived from patched in-memory data
    counts_p1 = _compute_counts(serialised_p1)
    # urls_count + last_scan_at come from the scan_run timestamp
    counts_p1["urls_count"] = len(ctx["url_rows"])
    counts_p1["last_scan_at"] = ctx["scan_run"]["finished_at"]
    _validate(FindingsCountsResponse, counts_p1)
    _write_fixture("findings/counts-populated.json", counts_p1)

    # findings/counts-empty.json
    counts_empty = _compute_counts([])
    _validate(FindingsCountsResponse, counts_empty)
    _write_fixture("findings/counts-empty.json", counts_empty)

    # findings/finding-updated.json: pick a real finding, flip status to fixed
    sample = copy.deepcopy(serialised_p1[0])
    sample["status"] = "fixed"
    sample["triaged_at"] = "2026-04-30T16:00:00+00:00"
    sample["triaged_by"] = "analyst_web"
    _write_fixture("findings/finding-updated.json", sample)

    # findings/finding-locked-error.json: small enough to inline.
    locked_id = int(serialised_p1[2]["id"])
    scan_id = int(ctx["scan_run"]["id"])
    locked = {
        "error": {
            "code": "FINDING_LOCKED",
            "message": (
                f"Finding {locked_id} is currently held by job scan:S-{scan_id}"
            ),
            "details": {
                "conflicting_ids": [locked_id],
                "holders": {str(locked_id): f"scan:S-{scan_id}"},
            },
        }
    }
    _write_fixture("findings/finding-locked-error.json", locked)

    return {
        "p1_serialised": serialised_p1,
        "p2_serialised": serialised_p2,
        # Restrict the segment-keyed id pool to ids actually present in the
        # published page-1 + page-2 fixtures (first 100). Triage / report
        # cross-references stay reachable via the finding-detail endpoint
        # the MSW handler builds from those fixtures.
        "p1_finding_ids_by_segment": _by_segment_ids(serialised_p1[:100]),
    }


def _by_segment_ids(serialised: list[dict]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for f in serialised:
        seg = f.get("segment")
        if seg:
            out[seg].append(int(f["id"]))
    return out


def _count_pairs(values: Iterable[Any]) -> list[dict]:
    counts: dict[Any, int] = defaultdict(int)
    for v in values:
        if v is None or v == "":
            continue
        counts[v] += 1
    return [{"value": v, "count": c} for v, c in counts.items() if c > 0]


def produce_findings_filter_options(ctx: dict, findings_meta: dict) -> None:
    """Emit findings/filter-options-{empty,populated}.json.

    Mirrors ``GET /findings/filter-options``: per-dimension value+count
    lists derived from the published page-1 + page-2 fixtures.
    """
    print("Producing findings/filter-options...")
    rows = findings_meta["p1_serialised"][:100]
    repo_name_by_id = {int(r["id"]): r["name"] for r in ctx["repo_rows"]}

    repo_counts: dict[int, int] = defaultdict(int)
    for r in rows:
        rid = r.get("repo_id")
        if isinstance(rid, int):
            repo_counts[rid] += 1

    # finding_type is a list-typed column, so flatten before counting.
    finding_types: list[str] = []
    for r in rows:
        for ft in r.get("finding_type") or []:
            finding_types.append(ft)

    populated = {
        "severity": _count_pairs(r.get("severity") for r in rows),
        "status": _count_pairs(r.get("status") for r in rows),
        "confidence": _count_pairs(r.get("confidence") for r in rows),
        "domain": _count_pairs(r.get("domain") for r in rows),
        "segment": _count_pairs(r.get("segment") for r in rows),
        "tool": _count_pairs(r.get("tool") for r in rows),
        "finding_type": _count_pairs(finding_types),
        "repo": [
            {
                "value": rid,
                "label": repo_name_by_id.get(rid, str(rid)),
                "count": count,
            }
            for rid, count in repo_counts.items()
        ],
    }
    _validate(FindingsFilterOptionsResponse, populated)
    _write_fixture("findings/filter-options-populated.json", populated)

    empty = {
        "severity": [],
        "status": [],
        "confidence": [],
        "domain": [],
        "segment": [],
        "tool": [],
        "finding_type": [],
        "repo": [],
    }
    _validate(FindingsFilterOptionsResponse, empty)
    _write_fixture("findings/filter-options-empty.json", empty)


# ---------------------------------------------------------------------------
# URL findings
# ---------------------------------------------------------------------------


def _serialise_url_row(row: dict, project_id: int, repo_name_by_id: dict[int, str]):
    """Reimplement web.api.url_list._row_to_dict against a raw DB row."""
    meta_raw = row.get("meta") or "{}"
    try:
        meta = json.loads(meta_raw)
    except (json.JSONDecodeError, TypeError):
        meta = {}
    return {
        "id": row["id"],
        "project_id": project_id,
        "repo_id": row["repo_id"],
        "repo_name": repo_name_by_id.get(row["repo_id"], ""),
        "source": row["source"],
        "tool": row["tool"],
        "run_id": row["run_id"],
        "method": row["method"],
        "protocol": row["protocol"],
        "host": row["host"],
        "port": row["port"],
        "path": row["path"],
        "file_path": row["file_path"],
        "meta": meta,
        "created_at": row["created_at"],
    }


def produce_url_findings(ctx: dict) -> None:
    print("Producing url_findings/...")
    repo_name_by_id = {int(r["id"]): r["name"] for r in ctx["repo_rows"]}
    items_p1 = [
        _serialise_url_row(r, ctx["project_1_id"], repo_name_by_id)
        for r in ctx["url_rows"]
    ]
    items_p2 = [
        _serialise_url_row(r, ctx["project_2_id"], repo_name_by_id)
        for r in ctx["url_rows"]
    ]

    for slug, items in (("project-1", items_p1), ("project-2", items_p2)):
        envelope = {
            "items": items,
            "total": len(items),
            "offset": 0,
            "limit": 100,
        }
        _write_fixture(f"url_findings/{slug}.json", envelope)

    _write_fixture(
        "url_findings/empty.json",
        {"items": [], "total": 0, "offset": 0, "limit": 100},
    )


def produce_url_list_filter_options(ctx: dict) -> None:
    """Emit url_findings/filter-options-{empty,populated}.json.

    Mirrors ``GET /url-list/filter-options``: per-dimension counts over
    the active url-row set. ``port`` carries integer values without a
    label; ``repo`` carries (id, name) pairs.
    """
    print("Producing url_findings/filter-options...")
    rows = ctx["url_rows"]
    repo_name_by_id = {int(r["id"]): r["name"] for r in ctx["repo_rows"]}

    port_counts: dict[int, int] = defaultdict(int)
    for r in rows:
        port = r.get("port")
        if isinstance(port, int):
            port_counts[port] += 1

    repo_counts: dict[int, int] = defaultdict(int)
    for r in rows:
        rid = r.get("repo_id")
        if isinstance(rid, int):
            repo_counts[rid] += 1

    populated = {
        "method": _count_pairs(r.get("method") for r in rows),
        "protocol": _count_pairs(r.get("protocol") for r in rows),
        "host": _count_pairs(r.get("host") for r in rows),
        "port": [
            {"value": port, "count": count} for port, count in port_counts.items()
        ],
        "path": _count_pairs(r.get("path") for r in rows),
        "repo": [
            {
                "value": rid,
                "label": repo_name_by_id.get(rid, str(rid)),
                "count": count,
            }
            for rid, count in repo_counts.items()
        ],
    }
    _validate(UrlListFilterOptionsResponse, populated)
    _write_fixture("url_findings/filter-options-populated.json", populated)

    empty = {
        "method": [],
        "protocol": [],
        "host": [],
        "port": [],
        "path": [],
        "repo": [],
    }
    _validate(UrlListFilterOptionsResponse, empty)
    _write_fixture("url_findings/filter-options-empty.json", empty)


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------


def _scan_summary_from_dict(row: dict) -> dict:
    """Coerce a DB-row-shape scan_runs dict into ScanRunSummary wire shape."""
    repo_ids = row.get("repo_ids")
    tool_ids = row.get("tool_ids")
    domains = row.get("domains")
    if isinstance(repo_ids, str):
        repo_ids = json.loads(repo_ids or "[]")
    if isinstance(tool_ids, str):
        tool_ids = json.loads(tool_ids or "[]")
    if isinstance(domains, str):
        domains = json.loads(domains or "[]")

    return {
        "id": int(row["id"]),
        "project_id": (
            int(row["project_id"]) if row.get("project_id") is not None else None
        ),
        "status": row.get("status"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "repo_ids": repo_ids or [],
        "tool_ids": tool_ids or [],
        "domains": domains or [],
        "findings_count": row.get("findings_count"),
        "skip_enrichment": bool(row.get("skip_enrichment")),
    }


def _enrich_real_scan(ctx: dict) -> dict:
    """The real scan_run has empty repo_ids/tool_ids/domains. Derive them
    from run_tools so the fixture displays meaningful values."""
    base = _scan_summary_from_dict(ctx["scan_run"])
    tools = sorted({t["tool"] for t in ctx["tool_runs"] if t.get("tool")})
    domains = sorted({t["domain"] for t in ctx["tool_runs"] if t.get("domain")})
    repos_active = [r for r in ctx["repo_rows"] if r.get("deleted_at") in (None, "")]
    repo_names = [r["name"] for r in repos_active]
    base["tool_ids"] = tools
    base["domains"] = domains
    base["repo_ids"] = repo_names
    return base


def produce_scans(ctx: dict) -> None:
    print("Producing scans/...")
    real_summary_p1 = _enrich_real_scan(ctx)
    real_summary_p2 = dict(real_summary_p1)
    real_summary_p2["project_id"] = ctx["project_2_id"]
    real_summary_p2["id"] = (
        real_summary_p1["id"] + 2000
    )  # avoid cross-fixture collision

    extras = _read_json(SEEDS_DIR / "scans/synthetic_runs.json")
    extras = _strip_comments(extras)
    p1_extra_summaries = [
        _scan_summary_from_dict(r) for r in extras["project_1_extras"]
    ]
    p2_extra_summaries = [
        _scan_summary_from_dict(r) for r in extras["project_2_extras"]
    ]

    p1_items = [real_summary_p1, *p1_extra_summaries]
    p2_items = [real_summary_p2, *p2_extra_summaries]

    # Validate via Pydantic.
    for item in p1_items + p2_items:
        ScanRunSummary.model_validate(item)

    _write_fixture(
        "scans/history-project-1.json",
        {"items": p1_items, "total": len(p1_items), "offset": 0, "limit": 20},
    )
    _validate(
        ScansListResponse,
        {"items": p1_items, "total": len(p1_items), "offset": 0, "limit": 20},
    )

    _write_fixture(
        "scans/history-project-2.json",
        {"items": p2_items, "total": len(p2_items), "offset": 0, "limit": 20},
    )
    _validate(
        ScansListResponse,
        {"items": p2_items, "total": len(p2_items), "offset": 0, "limit": 20},
    )

    _write_fixture(
        "scans/history-empty.json",
        {"items": [], "total": 0, "offset": 0, "limit": 20},
    )

    # scan-config: {repos, tools, domains}. ScanConfigResponse is the schema.
    repos_p1 = _build_scan_config_repos(ctx)
    tools_catalog = _read_json(SEEDS_DIR / "config/tool-catalog.json")
    tools_catalog = _strip_comments(tools_catalog)
    tools_p1 = [
        {
            "id": t["id"],
            "name": t["name"],
            "domain": t["domain"],
            "enabled": True,
        }
        for t in tools_catalog["items"]
    ]
    domains = ["sast", "sca", "web", "secrets"]
    config_p1 = {"repos": repos_p1, "tools": tools_p1, "domains": domains}
    _validate(ScanConfigResponse, config_p1)
    _write_fixture("scans/config-project-1.json", config_p1)
    _write_fixture("scans/config-project-2.json", config_p1)
    _write_fixture(
        "scans/config-empty.json",
        {"repos": [], "tools": tools_p1, "domains": domains},
    )


def _build_scan_config_repos(ctx: dict) -> list[dict]:
    """Construct ScanConfigRepo entries from the repositories table.

    Mirrors ``web/api/scans.py:get_scans_config``. ``source`` is the
    comma-joined repo type list (e.g. ``"ui,api"``) and ``location`` is
    ``"docker"`` when a container is configured else ``"local"``.
    """
    repos = []
    for db_row in ctx["repo_rows"]:
        if db_row.get("deleted_at"):
            continue
        repo = _repo_row_to_dict(db_row)
        types = repo.get("type") or []
        repos.append(
            {
                "id": repo["id"],
                "name": repo["name"],
                "source": ",".join(types) or "unknown",
                "location": "docker" if repo.get("container_name") else "local",
            }
        )
    return repos


# ---------------------------------------------------------------------------
# Repositories / Config
# ---------------------------------------------------------------------------


def _serialise_repository(repo: dict) -> dict:
    """Mirror ``web.api.projects._serialize_repo``: drop ``auth``, inject
    ``id`` + ``endpoint_file``.

    ``repo`` is the Repository-shape dict returned by ``_repo_row_to_dict``.
    """
    data = {k: v for k, v in repo.items() if k != "auth"}
    seed = data.pop("url_seed_file", None)
    data["endpoint_file"] = Path(seed).name if seed else None
    return data


def produce_repositories(ctx: dict) -> None:
    print("Producing config/repositories...")
    items = [
        _serialise_repository(_repo_row_to_dict(row))
        for row in ctx["repo_rows"]
        if not row.get("deleted_at")
    ]

    envelope_p1 = {
        "items": items,
        "total": len(items),
        "offset": 0,
        "limit": 500,
    }
    _write_fixture("config/repositories-project-1.json", envelope_p1)
    _write_fixture("config/repositories-project-2.json", envelope_p1)
    _write_fixture(
        "config/repositories-empty.json",
        {"items": [], "total": 0, "offset": 0, "limit": 500},
    )

    # Single repo detail (config/repository.json, used by /repositories/:id)
    if items:
        _write_fixture("config/repository.json", items[0])


def produce_project_info(ctx: dict, findings_meta: dict) -> None:
    print("Producing config/project-info...")
    proj = ctx["dvpa_project"]
    finding_count = len(findings_meta["p1_serialised"])
    repo_count = sum(1 for r in ctx["repo_rows"] if not r.get("deleted_at"))

    info_1 = {
        "id": ctx["project_1_id"],
        "name": ctx["project_1_name"],
        "code": ctx["project_1_code"],
        "company_name": proj.get("company_name", ""),
        "department_name": proj.get("department_name", ""),
        "abbreviation": proj.get("abbreviation", ctx["project_1_code"]),
        "created_at": ctx["project_1"]["created_at"],
        "path": ctx["project_1"]["path"],
        "repo_count": repo_count,
        "finding_count": finding_count,
    }
    _validate(ProjectInfoResponse, info_1)
    _write_fixture("config/project-info-1.json", info_1)

    info_2 = {
        "id": ctx["project_2_id"],
        "name": ctx["project_2_name"],
        "code": ctx["project_2_code"],
        "company_name": ctx["project_2_name"],
        "department_name": "",
        "abbreviation": ctx["project_2_code"],
        "created_at": ctx["project_2"]["created_at"],
        "path": ctx["project_2"]["path"],
        "repo_count": repo_count,
        "finding_count": finding_count,
    }
    _validate(ProjectInfoResponse, info_2)
    _write_fixture("config/project-info-2.json", info_2)


def produce_tool_catalog() -> None:
    print("Producing config/tool-catalog...")
    raw = _read_json(SEEDS_DIR / "config/tool-catalog.json")
    raw = _strip_comments(raw)
    payload = {"items": raw["items"], "total": len(raw["items"])}
    _validate(ToolCatalogResponse, payload)
    _write_fixture("config/tool-catalog.json", payload)


def produce_tool_overrides() -> None:
    print("Producing config/tool-overrides...")
    raw = _read_json(SEEDS_DIR / "config/tool-overrides-templates.json")
    raw = _strip_comments(raw)
    for slug, payload in (
        ("project-1", raw["project_1"]),
        ("project-2", raw["project_2"]),
        ("empty", raw["empty"]),
    ):
        _validate(ToolOverrideListResponse, payload)
        _write_fixture(f"config/tool-overrides-{slug}.json", payload)


# ---------------------------------------------------------------------------
# Projects (top-level list + meta)
# ---------------------------------------------------------------------------


def produce_projects(ctx: dict, findings_meta: dict) -> None:
    print("Producing projects/...")
    items = []
    for p in ctx["projects"]:
        items.append(
            {
                "id": int(p["id"]),
                "name": p["name"],
                "code": _derive_code(p["name"]),
                "created_at": p["created_at"],
            }
        )
    list_envelope = {
        "items": items,
        "total": len(items),
        "offset": 0,
        "limit": 50,
    }
    _validate(ProjectListResponse, list_envelope)
    _write_fixture("projects/list.json", list_envelope)

    repo_count = sum(1 for r in ctx["repo_rows"] if not r.get("deleted_at"))
    finding_count = len(findings_meta["p1_serialised"])
    enabled_tools = sorted(
        {f["tool"] for f in findings_meta["p1_serialised"] if f.get("tool")}
    )
    meta_populated = {
        "id": ctx["project_1_id"],
        "name": ctx["project_1_name"],
        "code": ctx["project_1_code"],
        "repo_count": repo_count,
        "url_list_count": len(ctx["url_rows"]),
        "finding_count": finding_count,
        "enabled_tools": enabled_tools,
    }
    _validate(ProjectMetaResponse, meta_populated)
    _write_fixture("projects/meta-populated.json", meta_populated)

    meta_empty = {
        "id": 999,
        "name": "empty-project",
        "code": "EMP",
        "repo_count": 0,
        "url_list_count": 0,
        "finding_count": 0,
        "enabled_tools": [],
    }
    _validate(ProjectMetaResponse, meta_empty)
    _write_fixture("projects/meta-empty.json", meta_empty)


# ---------------------------------------------------------------------------
# Triage / Reports / Chat: wire-shape templates
# ---------------------------------------------------------------------------


def _substitute(payload: Any, ctx: dict, extras: dict) -> Any:
    """Recursively replace {{type:key}} string tokens with values from ctx."""
    bag = {**ctx, **extras}

    def lookup(token: str):
        # token format: type:key, where type is one of int, str, ints
        kind, _, key = token.partition(":")
        val = bag.get(key)
        if val is None:
            raise KeyError(f"placeholder {{{{{token}}}}} unresolved (key={key})")
        if kind == "int":
            return int(val)
        if kind == "str":
            return str(val)
        if kind == "ints":
            return [int(x) for x in val]
        raise ValueError(f"unknown placeholder kind {kind!r}")

    if isinstance(payload, dict):
        return {k: _substitute(v, ctx, extras) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_substitute(x, ctx, extras) for x in payload]
    if isinstance(payload, str):
        # Whole-string token: return the typed value (preserves int/list).
        if (
            payload.startswith("{{")
            and payload.endswith("}}")
            and payload.count("{{") == 1
        ):
            return lookup(payload[2:-2])
        # Embedded token(s): replace each occurrence with str(value). Only
        # match our typed tokens (kind is one of int, str, ints) so GitHub's
        # ${{...}} in real finding descriptions is left untouched.
        import re as _re

        def _repl(m: _re.Match) -> str:
            return str(lookup(m.group(1)))

        return _re.sub(r"\{\{(int:[^}]+|str:[^}]+|ints:[^}]+)\}\}", _repl, payload)
    return payload


def produce_triage(ctx: dict, findings_meta: dict) -> None:
    print("Producing triage/...")
    raw = _read_json(SEEDS_DIR / "triage/templates.json")
    raw = _strip_comments(raw)

    seg_ids = findings_meta["p1_finding_ids_by_segment"]

    def _slice(seg: str, n: int) -> list[int]:
        return seg_ids.get(seg, [])[:n]

    extras = {
        "scan_run_id_real": ctx["scan_run"]["id"],
        "scan_started_at": ctx["scan_run"]["started_at"],
        "scan_finished_at": ctx["scan_run"]["finished_at"],
        "findings_total_p1": len(findings_meta["p1_serialised"]),
        "finding_ids_p1_sast_5": _slice("sast", 5),
        "finding_ids_p1_web_5": _slice("web", 5),
        "finding_ids_p1_secrets_5": _slice("secrets", 5),
    }

    mapping = (
        ("active-running.json", "active_running", TriageRunSummary),
        ("active-null.json", "active_null", None),
        ("latest-completed.json", "latest_completed", TriageRunSummary),
        ("start-202.json", "start_202", TriageRunSummary),
        ("resume-202.json", "resume_202", TriageRunSummary),
        ("cancel-202.json", "cancel_202", TriageCancelResponse),
        ("detail-project-1.json", "detail_project_1", TriageDetailResponse),
        ("history-project-1.json", "history_project_1", TriagesListResponse),
        ("history-project-2.json", "history_project_2", TriagesListResponse),
        ("history-empty.json", "history_empty", TriagesListResponse),
    )
    for fname, key, model in mapping:
        rendered = _substitute(raw[key], ctx, extras)
        if model is not None:
            _validate(model, rendered)
        _write_fixture(f"triage/{fname}", rendered)


def produce_reports(ctx: dict) -> None:
    print("Producing reports/...")
    raw = _read_json(SEEDS_DIR / "reports/templates.json")
    raw = _strip_comments(raw)

    extras = {
        "scan_run_id_real": ctx["scan_run"]["id"],
        "scan_started_at": ctx["scan_run"]["started_at"],
        "scan_finished_at": ctx["scan_run"]["finished_at"],
    }

    mapping = (
        ("drafts-project-1.json", "drafts_project_1", None),
        ("drafts-project-2.json", "drafts_project_2", None),
        ("drafts-empty.json", "drafts_empty", None),
        ("history-project-1.json", "history_project_1", ReportsListResponse),
        ("history-empty.json", "history_empty", ReportsListResponse),
        ("latest-project-1.json", "latest_project_1", ReportSummary),
        ("generate-202.json", "generate_202", ReportSummary),
        ("draft-start-202.json", "draft_start_202", None),
        ("draft-upload-200.json", "draft_upload_200", None),
        ("cancel-202.json", "cancel_202", None),
    )
    for fname, key, model in mapping:
        rendered = _substitute(raw[key], ctx, extras)
        if model is not None:
            _validate(model, rendered)
        _write_fixture(f"reports/{fname}", rendered)


def produce_chat(ctx: dict) -> None:
    print("Producing chat/...")
    raw = _read_json(SEEDS_DIR / "chat/templates.json")
    raw = _strip_comments(raw)
    extras: dict[str, Any] = {}

    mapping = (
        ("sessions-project-1.json", "sessions_project_1", ChatSessionsListResponse),
        ("sessions-project-2.json", "sessions_project_2", ChatSessionsListResponse),
        ("sessions-empty.json", "sessions_empty", ChatSessionsListResponse),
        ("messages-session-101.json", "messages_session_101", ChatMessagesListResponse),
        ("messages-empty.json", "messages_empty", ChatMessagesListResponse),
        ("create-session-201.json", "create_session_201", ChatSessionSummary),
        ("send-message-202.json", "send_message_202", ChatMessageSendResponse),
        ("cancel-202.json", "cancel_202", None),
    )
    for fname, key, model in mapping:
        rendered = _substitute(raw[key], ctx, extras)
        if model is not None:
            _validate(model, rendered)
        _write_fixture(f"chat/{fname}", rendered)


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------


def produce_runtime() -> None:
    print("Producing runtime/...")
    for src, dst in (
        ("runtime/deps-claude-installed.json", "runtime/deps-claude-installed.json"),
        ("runtime/deps-claude-missing.json", "runtime/deps-claude-missing.json"),
    ):
        _write_fixture(dst, _read_json(SEEDS_DIR / src))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    print(f"Generator running. Output: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ctx = build_context()

    # Silence unused-import warnings: these are loaded for side-effect of
    # being importable, not to invoke directly here.
    _ = (ScanCancelResponse,)

    findings_meta = produce_findings(ctx)
    produce_findings_filter_options(ctx, findings_meta)
    produce_url_findings(ctx)
    produce_url_list_filter_options(ctx)
    produce_scans(ctx)
    produce_repositories(ctx)
    produce_project_info(ctx, findings_meta)
    produce_tool_catalog()
    produce_tool_overrides()
    produce_projects(ctx, findings_meta)
    produce_triage(ctx, findings_meta)
    produce_reports(ctx)
    produce_chat(ctx)
    produce_runtime()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
