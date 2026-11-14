# Adding a New Tool Wrapper

This guide walks you through integrating a new security scanner into tally. After
following it, you will have a tool that:

- Runs automatically in the appropriate scan segment (`scan`, `scan --domain=sast`, etc.)
- Has its findings ingested into ChromaDB and SQLite for `search` and `chat`
- Appears in `tool list` and `tool add` setup

> **Required:** After writing the wrapper files you must register the tool in
> `config/commands.json` (Step 5). The wrapper files alone are not enough.
> Tally only loads tools that appear in that file.

---

## Architecture overview

Each tool integration consists of up to four files:

```
infrastructure/tools/wrappers/
  base/<tool_name>.py          # Abstract base: behavior shared by local + docker
  local/<tool_name>.py         # Concrete local wrapper (runs binary on host)
  docker/<tool_name>.py        # Concrete docker wrapper (runs inside container)

infrastructure/tools/parsers/<tool_name>.py  # Parser + ToolHandler in one file
                                             # (normalize, render, fingerprint_key,
                                             # normalized_fields)
```

File stems use **underscores** for multi-word names (e.g. `pip_audit.py` for `pip-audit`).
The auto-discovery system converts underscores back to hyphens for the tool name.

### How discovery works

On startup `discover_tools()` reads `config/commands.json`. For each configured tool it
imports `infrastructure.tools.wrappers.<location>.<stem>` and instantiates the wrapper
class, then registers it in `tool_registry`. Manual registration is not needed.

`ToolHandlerFactory.load(tool_name)` imports `infrastructure.tools.parsers.<stem>` and
finds the class whose `tool_name` attribute matches. This single file handles SQLite
ingestion (`normalize`), ChromaDB rendering (`render`), and deduplication
(`fingerprint_key`).

---

## Step 1: Base class

`infrastructure/tools/wrappers/base/<tool_name>.py` defines all tool-level behavior
shared by local and Docker wrappers.

```python
"""Shared base class for <tool-name> local and docker wrappers."""

from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface


class Base<ToolName>Tool(ToolInterface):

    _candidate_commands: list[str] = ["<binary-name>"]
    _command_entry_type: str = "repo"   # or "api" for ZAP-style scanners

    @property
    def name(self) -> str:
        return "<tool-name>"   # kebab-case, matches commands.json key

    @property
    def category(self) -> str:
        return "<segment>"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "..."

    @property
    def scan_segment(self) -> str:
        # "sast" / "sca" / "secrets" / "api"
        return "<segment>"

    @property
    def findings_exit_ok(self) -> bool:
        return True   # True for tools that exit non-zero when findings exist

    @property
    def language_gates(self) -> list[str]:
        return []   # [] = run on all repos; ["python"] = Python repos only

    @property
    def requires_base_urls(self) -> bool:
        return False   # True for DAST scanners needing repo.base_urls

    @property
    def always_run(self) -> bool:
        return True   # False for language-gated auditors

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", len(parsed_data.get("findings", [])))
```

### `ExecutionPass` parameters

The template above shows the two required fields. `ExecutionPass` also accepts
optional fields for tools that need environment overrides, working directory
control, or stdin-based invocation:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `label_suffix` | str | (required) | Label for output files and progress display |
| `kwargs` | dict | (required) | Passed as `**kwargs` to `build_command()` |
| `cwd` | str or None | None | Working directory override for the subprocess |
| `env` | dict or None | None | Environment variables injected into the subprocess |
| `stdin_data` | str or None | None | Data piped to the tool's stdin |

Tools that receive configuration via environment variables (e.g. endpoint URLs,
model names, timeout values) set `env` on the pass. Tools that accept a JSON
payload via stdin instead of command-line arguments set `stdin_data`. Both are
forwarded through the executor to the subprocess runner.

### `always_run` vs `language_gates`

| `always_run` | `language_gates` | Behavior |
|---|---|---|
| `True` | `[]` | Runs on every repo |
| `True` | `["python"]` | Runs on every repo (`always_run` overrides gates) |
| `False` | `[]` | Runs on every repo (no restriction) |
| `False` | `["python"]` | Runs only on Python repos |

---

## Step 2: Local wrapper

```python
"""<tool-name> local wrapper."""

import shutil
from pathlib import Path
from typing import Any

from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.<tool_name> import Base<ToolName>Tool


class <ToolName>LocalTool(Base<ToolName>Tool):

    def __init__(self, config=None) -> None:
        pass

    @property
    def command(self) -> str:
        return "<binary>"

    def check_available(self) -> bool:
        return shutil.which(self.command) is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs) -> list[str]:
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required")
        return [self.command, "--format", "json", repo_path]
```

---

## Step 3: Docker wrapper

```python
"""<tool-name> docker wrapper."""

from infrastructure.tools.wrappers.base.<tool_name> import Base<ToolName>Tool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class <ToolName>DockerTool(Base<ToolName>Tool):

    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_command(self, **kwargs) -> list[str]:
        repo_path: str = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'repo edit' to set the container mount path."
            )
        tool_args = ["--format", "json", repo_path]
        return build_docker_exec(self._container_name, self._tool_path, tool_args)
```

`build_docker_exec(container, tool_path, tool_args, workdir=None)` produces:
`docker exec [-w workdir] <container> <tool_path> <tool_args...>`

---

## Step 4: Parser + Handler

`infrastructure/tools/parsers/<tool_name>.py` is a **single file** containing both the
output parser functions and the `ToolHandler` class. The handler is the only file the
ingestion pipeline needs beyond the wrappers.

```python
"""Parser and handler for <tool> output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta


# ---------------------------------------------------------------------------
# Parser functions
# ---------------------------------------------------------------------------


def parse_<tool_name>_json(json_path: Path) -> dict[str, Any]:
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"JSON parse error: {exc}"}
    return _parse_data(data)


def parse_<tool_name>_json_string(json_string: str) -> dict[str, Any]:
    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as exc:
        return {"error": f"JSON parse error: {exc}", "raw_output": json_string}
    return _parse_data(data)


def _parse_data(data: dict[str, Any]) -> dict[str, Any]:
    results = data.get("results", [])
    findings = [_parse_finding(r) for r in results]
    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


def _parse_finding(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": result.get("check_id", ""),
        "severity": result.get("severity", "low"),
        "message": result.get("message", ""),
        "file_path": result.get("path", ""),
        "line_start": result.get("start", {}).get("line", ""),
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class <ToolName>Handler:
    tool_name = "<tool-name>"   # kebab-case, must match wrapper name property
    domain = "code"             # "code" or "web"
    segment = "<segment>"       # matches scan_segment on the wrapper
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability"},
    }
    should_enrich = True
    should_visualize = True
    enrichment_fields = None

    # Fields shown by `search --show-fields --tool=<name>`
    normalized_fields: list[str] = [
        "confidence",
        "file_path",
        "finding_type",
        "rule_id",
        "severity",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])
        source_file = _first_output_file(result.output_files)
        rows: list[dict] = []
        for finding in findings:
            row: dict[str, Any] = {
                "tool": self.tool_name,
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": finding.get("severity", "low"),
                "rule_id": finding.get("rule_id", ""),
                "file_path": finding.get("file_path", ""),
                "description": finding.get("message", ""),
                "timestamp": result.timestamp,
                "source_file": source_file,
            }
            row.update(_shared_meta(self, "vulnerability"))
            rows.append(row)
        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Rule: {row.get('rule_id', '')}",
            f"File: {row.get('file_path', '')}",
            f"Severity: {row.get('severity', '')}",
        ]
        if row.get("description"):
            parts.append(f"Description: {row['description']}")
        return f"[{self.tool_name}] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        """Stable deduplication key. Must be unique per logical finding."""
        return "|".join([
            self.tool_name,
            str(finding.get("rule_id", "")),
            str(finding.get("file_path", "")),
            str(finding.get("line_start", "")),
        ])
```

### Key handler attributes

| Attribute | Purpose |
|---|---|
| `tool_name` | Must exactly match the wrapper's `name` property |
| `domain` | `"code"` (SAST/SCA/secrets) or `"web"` (API/ZAP) |
| `segment` | Matches `scan_segment` on the wrapper |
| `non_enriched_fields` | Fields the tool provides; LLM enrichment skipped for these |
| `type_flags` | Maps finding_type string -> set of `type_*` boolean fields |
| `should_enrich` | `False` to skip LLM enrichment entirely |
| `normalized_fields` | Shown by `search --show-fields --tool=<name>` |

**`_shared_meta(self, finding_type)`** sets `domain`, `segment`, `enriched`, and all
`type_*` boolean columns. Always call `row.update(_shared_meta(self, "<finding_type>"))`.

**`fingerprint_key(finding)`** must return a stable string that uniquely identifies a
finding. Findings with the same key are treated as duplicates on re-scan.

### Severity normalization

Normalize early in the parser so downstream code never sees `"HIGH"` or `"CRITICAL"`:

```python
_SEVERITY_MAP = {
    "CRITICAL": "critical", "HIGH": "high",
    "MEDIUM": "medium", "LOW": "low", "INFO": "informational",
}
severity = _SEVERITY_MAP.get(raw.upper(), raw.lower())
```

### Common top-level output keys

```
"findings"         # SAST (semgrep pattern)
"vulnerabilities"  # SCA (pip-audit pattern)
"secrets"          # secrets (gitleaks pattern)
"alerts"           # API/ZAP pattern
```

The `count_findings` method in the base class must read whichever key you use.

### SCA shortcut

If your tool outputs `parsed_data["vulnerabilities"]` with the standard SCA fields,
use the shared helpers in `_sca_shared.py`:

```python
from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec

from ._sca_shared import (
    _SCA_COMMON_ENRICHMENT_FIELDS,
    _build_sca_normalize,
    _sca_fingerprint_key,
    _sca_render,
)


class GrypeHandler:
    tool_name = "grype"
    domain = "code"
    segment = "sca"
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }
    should_enrich = True
    should_visualize = True
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = _SCA_COMMON_ENRICHMENT_FIELDS
    normalized_fields: list[str] = [
        "confidence", "ecosystem", "finding_type",
        "package_name", "package_version", "severity", "vulnerability_id",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        return _build_sca_normalize(self, result, profile)

    def render(self, row: dict) -> str:
        return _sca_render(row)

    def fingerprint_key(self, finding: dict) -> str:
        return _sca_fingerprint_key("grype", finding)
```

---

## Step 5: Register in `commands.json`

Either run `tool add` in the REPL or write the entry manually:

**Local binary:**
```json
"<tool-name>": {
  "type": "repo",
  "location": "local",
  "path": "/usr/local/bin/<binary>"
}
```

**Docker container:**
```json
"<tool-name>": {
  "type": "repo",
  "location": "docker",
  "container": {
    "name": "my-container",
    "tool_path": "/usr/local/bin/<binary>"
  }
}
```

---

## Step 6: Verify

### Handler is discovered

```bash
.venv/bin/python -c "from application.rag.ingestor import ToolHandlerFactory; h = ToolHandlerFactory.load('<tool-name>'); print(h); print(h.fingerprint_key({'rule_id': 'test'}))"
```

### Wrapper is registered

```bash
.venv/bin/python -c "from application.tools.registry import ToolRegistry, discover_tools; r = ToolRegistry(); discover_tools('.', r); t = r.get_tool('<tool-name>'); print(t, t.check_available(), t.scan_segment)"
```

### Parse round-trip

```bash
.venv/bin/python -c "from infrastructure.tools.parsers.<tool_name> import parse_<tool_name>_json_string; r = parse_<tool_name>_json_string('{}'); assert 'error' not in r; print(r.keys())"
```

### Linter and type checker

```bash
.venv/bin/ruff check infrastructure/tools/wrappers/base/<tool_name>.py infrastructure/tools/wrappers/local/<tool_name>.py infrastructure/tools/parsers/<tool_name>.py
.venv/bin/pyright infrastructure/tools/wrappers/base/<tool_name>.py infrastructure/tools/wrappers/local/<tool_name>.py infrastructure/tools/parsers/<tool_name>.py
```

### Test suite

```bash
.venv/bin/pytest tests/unit/ -q --tb=short
```

---

## Advanced patterns

Not every tool follows the simple binary-in, JSON-out pattern. This section covers
patterns for tools with external service dependencies, non-standard output handling,
or partial failure modes. See the Antares adapter for a real example of all three.

### External service lifecycle

Some tools require a companion process (e.g. an API shim or proxy) running during
the scan. Manage the lifecycle in `build_execution_passes` (start) and
`merge_pass_results` (stop):

```python
def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
    self._service = start_companion_service()
    try:
        return [ExecutionPass(
            label_suffix=context.repo.name,
            kwargs={},
            env={"SERVICE_URL": self._service.url},
        )]
    except Exception:
        self._service.stop()
        raise

def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
    try:
        return pass_results[0]
    finally:
        if self._service is not None:
            self._service.stop()
```

Use a `try/finally` in `merge_pass_results` so the companion process is stopped
even when the scan fails.

### Overriding `parse_output`

The default `parse_output` on `ToolInterface` reads the tool's stdout file and
passes it to the parser. Override it when the tool writes output to non-standard
locations (temp directories, multiple files) or when you need to post-process
trace data:

```python
def parse_output(
    self,
    output: str,
    files: dict[str, Path],
) -> dict[str, Any]:
    json_path = files.get("stdout")
    if json_path is not None and json_path.exists():
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        parsed = parse_tool_data(data)
    else:
        parsed = parse_tool_json_string(output)

    if self._trace_dir is not None:
        parsed["traces"] = load_traces(self._trace_dir)
    return parsed
```

### Partial failure handling

Tools that exit non-zero on partial failures (some workers failed, some
succeeded) are marked `success=False` by the executor. If the output still
contains valid findings, override `merge_pass_results` to recover:

```python
def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
    result = pass_results[0]
    if (
        not result.success
        and result.parsed_data
        and result.parsed_data.get("findings")
    ):
        result = ToolResult(
            tool_name=result.tool_name,
            success=True,
            output=result.output,
            parsed_data=result.parsed_data,
            output_files=result.output_files,
            timestamp=result.timestamp,
            duration_seconds=result.duration_seconds,
            finding_count=result.finding_count,
            repo=result.repo,
        )
    return result
```

### Docker-only or local-only tools

Not every tool needs both a local and a Docker wrapper. If the tool only runs
locally (e.g. it depends on a companion service that manages its own process),
skip the Docker wrapper file. The auto-discovery system loads whichever wrapper
matches the `location` field in `config/commands.json`.

---

## Common mistakes

**Missing `always_run` or `candidate_commands` on the base class**

Both are abstract on `ToolInterface`. Missing either raises `TypeError` at instantiation.

**`tool_name` mismatch between wrapper and handler**

`ToolHandlerFactory.load("npm-audit")` imports `infrastructure.tools.parsers.npm_audit`
and looks for `tool_name == "npm-audit"`. Underscores in the attribute value cause
silent ingestion failures.

**`fingerprint_key` not implemented**

Every handler must implement `fingerprint_key`. Omitting it causes duplicate findings
on re-scans because the fallback generic hash is less stable.

**`metadata` value is a list**

ChromaDB rejects list values. Join to comma-separated strings:
```python
meta["cwe"] = ", ".join(cwe_ids)
```

**Multiple ExecutionPasses but `merge_pass_results` returns only the first**

Implement `merge_pass_results` to combine all pass results. The default silently drops
passes after the first.

**`findings_exit_ok` is False for a tool that exits 1 on findings**

Most security scanners exit 1 when they find something. Set `findings_exit_ok = True`;
otherwise tally marks the result as failed and skips ingestion.
