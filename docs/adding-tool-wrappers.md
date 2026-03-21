# Adding a New Tool Wrapper

This guide walks through integrating a new security scanner into tally. After following it
you will have a tool that:

- Runs automatically in the appropriate scan segment (`scan`, `scan --domain=sast`, etc.)
- Has its findings ingested into ChromaDB and SQLite for `search` and `chat`
- Appears in `tool list` and `tool add` setup
- Requires **zero edits to any existing file**

---

## Architecture overview

Each tool integration consists of up to five files:

```
infrastructure/tools/wrappers/
  base/<tool_name>.py          # Abstract base: behaviour shared by local + docker
  local/<tool_name>.py         # Concrete local wrapper (runs binary on host)
  docker/<tool_name>.py        # Concrete docker wrapper (runs binary inside container)

application/rag/chunks/<tool_name>.py # Chunk builder: converts findings to ChromaDB documents

infrastructure/tools/parsers/<tool_name>_parser.py  # (optional) parses raw tool output
```

File stems use **underscores** for multi-word names (e.g. `pip_audit.py` for `pip-audit`).
The auto-discovery system converts underscores back to hyphens for the tool name, so
`pip_audit.py` registers as `pip-audit`.

### How discovery works

On startup `discover_tools()` reads `config/commands.json`. For each configured tool it
imports `infrastructure.tools.wrappers.<location>.<stem>` and instantiates the wrapper class found
there, then registers it in the global `tool_registry`. No manual imports or registration
calls are needed anywhere.

`FindingIngestor._default_builders()` independently scans `application/rag/chunks/` by glob and
loads a `ChunkBuilderFactory` instance for every `.py` file it finds (excluding `_`-prefixed
helpers like `_shared.py` and `sca.py`). So a new chunk file is auto-wired to ingestion
the moment it exists.

---

## Step 1 — Base class

`infrastructure/tools/wrappers/base/<tool_name>.py` defines all the tool-level behaviour that is
identical whether the binary runs locally or inside Docker. Both the local and Docker
concrete classes will inherit from it.

```python
"""Shared base class for <tool-name> local and docker wrappers."""

from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface


class Base<ToolName>Tool(ToolInterface):

    # -----------------------------------------------------------------------
    # Class-level attributes — read by commands_setup.py WITHOUT instantiation
    # -----------------------------------------------------------------------

    # Binary names to try with shutil.which() during `tool add` setup.
    # List them in preference order. Use the host-side binary name(s) here —
    # for tools where the binary name differs from the tool name (e.g. npm-audit
    # uses ["npm"]) list only what shutil.which would find.
    _candidate_commands: list[str] = ["<binary-name>"]

    # CommandEntry.type written to commands.json.
    # "repo"  — tool scans repository paths
    # "api"   — tool scans HTTP base URLs (e.g. ZAP); requires repo.base_urls
    _command_entry_type: str = "repo"

    # -----------------------------------------------------------------------
    # Identity properties
    # -----------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Canonical tool name. Kebab-case. Matches the key in commands.json."""
        return "<tool-name>"

    @property
    def category(self) -> str:
        """Human-readable category shown in `tool list`. Mirrors scan_segment."""
        return "<segment>"

    @property
    def scope(self) -> str:
        """'repository' for per-repo tools, 'project' for project-wide tools."""
        return "repository"

    @property
    def description(self) -> str:
        """One-line description shown in `tool list`."""
        return "..."

    # -----------------------------------------------------------------------
    # Scan orchestration properties
    # -----------------------------------------------------------------------

    @property
    def scan_segment(self) -> str:
        """Which scan domain this tool belongs to.

        "sast"    — static analysis (semgrep-style)
        "sca"     — dependency/supply-chain auditing (pip-audit-style)
        "secrets" — secret detection (gitleaks-style)
        "api"     — web/API scanning (zap-style)
        "network" — host/port scanning (nmap-style)
        """
        return "<segment>"

    @property
    def findings_exit_ok(self) -> bool:
        """True if the binary exits non-zero when it FINDS something.

        Most security scanners (semgrep, gitleaks, pip-audit, ZAP…) exit 1 when
        they report findings and 0 when clean. Set this to True for those tools so
        tally does not treat a finding-laden scan as a failure.

        Set to False for tools like nmap that exit 0 on success regardless of what
        they found.
        """
        return True

    @property
    def language_gates(self) -> list[str]:
        """Languages that must be present in a repo for this tool to run.

        Return an empty list for language-agnostic tools (semgrep, gitleaks, osv-scanner).
        Return a non-empty list to restrict the tool to matching repos:
          ["python"]                       — only Python repos
          ["javascript", "typescript", "node"]  — any JS/TS repo
          ["php"]                          — PHP only

        Language values come from repo.languages in the project config and are compared
        case-insensitively.
        """
        return []

    @property
    def requires_base_urls(self) -> bool:
        """True if the tool needs repo.base_urls to be configured.

        Use True for API/DAST scanners like ZAP that need an HTTP target. When True,
        repos without base_urls configured are silently skipped with a 'no base_urls'
        message.
        """
        return False

    @property
    def always_run(self) -> bool:
        """True if this tool should run on every repo-scan regardless of language gates.

        Tools with always_run=True are included in every `scan` invocation even when
        language_gates is non-empty (the gates are ignored for the 'always' decision).

        Typical values:
          True  — semgrep, gitleaks, osv-scanner, zap (run on all repos)
          False — pip-audit, npm-audit, composer-audit (only when language matches)
                  nmap (network tool, not part of repo scan at all)
        """
        return True

    @property
    def candidate_commands(self) -> list[str]:
        """Instance-level accessor for _candidate_commands. Do not override."""
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        """Legacy property used by some display code. Delegates to language_gates."""
        return self.language_gates or None

    # -----------------------------------------------------------------------
    # Execution
    # -----------------------------------------------------------------------

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return the list of subprocess invocations needed for one tool run.

        Most tools need a single pass per repo. Return multiple ExecutionPass objects
        only when you need to run the binary more than once and merge results (see
        gitleaks which runs dir + git passes).

        Each ExecutionPass.kwargs is forwarded to build_command() on the concrete class.
        """
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        """Combine results from all ExecutionPasses into a single ToolResult.

        For single-pass tools just return pass_results[0].
        For multi-pass tools (gitleaks) merge parsed_data and output_files here.
        """
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        """Return the total finding count from parsed_data.

        Used by the display layer to show "N findings" after a scan. Prefer reading
        from a summary key rather than len(list) so the count is available even when
        the list is truncated.
        """
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", len(parsed_data.get("findings", [])))
```

### `always_run` vs `language_gates`

These two properties interact during a `scan` (repo scan):

| `always_run` | `language_gates` | Behaviour |
|---|---|---|
| `True` | `[]` | Runs on every repo |
| `True` | `["python"]` | Runs on every repo (always_run overrides gates) |
| `False` | `[]` | Runs on every repo (no restriction) |
| `False` | `["python"]` | Runs only on repos whose languages include Python |

The distinction between `always_run=True` and `always_run=False, language_gates=[]` only
matters for RepoScan (the `scan --repo=<name>` code path). In practice: use `True` for
security tools that should never be skipped, `False` for language-specific auditors.

---

## Step 2 — Local wrapper

`infrastructure/tools/wrappers/local/<tool_name>.py` inherits from the base class and adds the
host-side execution details: where the binary lives and how to invoke it.

```python
"""<tool-name> local wrapper."""

import shutil
from pathlib import Path

from domain.tools.base import get_tool_version
from infrastructure.tools.wrappers.base.<tool_name> import Base<ToolName>Tool


class <ToolName>LocalTool(Base<ToolName>Tool):

    def __init__(self, config=None) -> None:
        # config is a CommandEntry (from commands.json). For simple tools that only
        # need the binary path, store config.path. For tools with no config
        # (fallback/dev mode), config may be None.
        self._path: str = config.path if config is not None else self.name

    @property
    def command(self) -> str:
        """The executable to run. Used by ToolWrapper.get_version()."""
        return self._path

    def check_available(self) -> bool:
        """Return True if the binary is usable."""
        return shutil.which(self._path) is not None or Path(self._path).exists()

    def get_version(self) -> str | None:
        """Return the version string shown in `tool list`. None is acceptable."""
        return get_tool_version(self._path)

    def build_command(self, **kwargs) -> list[str]:
        """Build the full argv list for one invocation.

        The executor calls build_command(**pass.kwargs) where pass.kwargs comes from
        the ExecutionPass you returned in build_execution_passes(). Typically:
          kwargs["repo_path"] — filesystem path to the repo being scanned
        """
        repo_path: str | None = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required")

        return [self._path, "--format", "json", repo_path]
```

The `__init__(self, config=None)` signature is required. When `commands.json` configures
a local binary tally passes a `CommandEntry` as `config`. In fallback/dev mode (no
`commands.json`) tally may pass `None`.

---

## Step 3 — Docker wrapper

`infrastructure/tools/wrappers/docker/<tool_name>.py` is structured identically to the local wrapper
but uses `build_docker_exec` to prefix the tool's args with `docker exec`.

```python
"""<tool-name> docker wrapper."""

from infrastructure.tools.wrappers.base.<tool_name> import Base<ToolName>Tool
from infrastructure.tools.wrappers.docker._docker_exec import build_docker_exec


class <ToolName>DockerTool(Base<ToolName>Tool):

    def __init__(self, config) -> None:
        # config is always a CommandEntry for docker — it is never None.
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        # Presence in commands.json means the user configured it. Trust them.
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

`build_docker_exec(container, tool_path, tool_args, workdir=None)` from
`infrastructure.tools.wrappers.docker._docker_exec` produces:

```
docker exec [<-w workdir>] <container> <tool_path> <tool_args…>
```

Use `workdir` when the tool needs to run with a specific working directory inside the
container (some tools read relative paths from cwd).

---

## Step 4 — Parser

If the tool produces JSON, write `infrastructure/tools/parsers/<tool_name>_parser.py`. Look at
`semgrep_parser.py` (JSON) or `nmap_parser.py` (XML) as reference implementations.

The parser module should expose two public functions:

```python
def parse_<tool_name>_json(json_path: Path) -> dict[str, Any]:
    """Parse a saved output file."""

def parse_<tool_name>_json_string(json_string: str) -> dict[str, Any]:
    """Parse raw stdout captured as a string."""
```

Both must return a dict. The only reserved key is `"error"` — if you set it, the ingestor
will skip ingestion for that result and log a warning.

### Normalised structure

There is no enforced schema, but the following conventions are used throughout the
codebase and the RAG chunk builders expect them:

```python
{
    # Primary findings list — name matches what your chunk builder will read
    "findings": [...],       # for SAST-style findings
    "secrets": [...],        # gitleaks convention
    "vulnerabilities": [...],# SCA convention (pip-audit, osv-scanner, …)
    "alerts": [...],         # ZAP convention
    "hosts": [...],          # nmap convention

    # Optional but helpful for `scan` display output
    "summary": {
        "total_findings": 42,
        "by_severity": {"high": 5, "medium": 30, "low": 7},
    },
}
```

### Severity normalisation

Tally uses lowercase severity values throughout. Normalise your tool's severity strings
early in the parser so downstream code never sees values like `"HIGH"` or `"CRITICAL"`:

```python
_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH":     "high",
    "MEDIUM":   "medium",
    "LOW":      "low",
    "INFO":     "informational",
}
severity = _SEVERITY_MAP.get(raw.upper(), raw.lower())
```

Call the parser from `parse_output()` on both the local and docker wrappers:

```python
def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
    from infrastructure.tools.parsers.<tool_name>_parser import (
        parse_<tool_name>_json,
        parse_<tool_name>_json_string,
    )
    json_path = files.get("stdout")
    if json_path is not None and json_path.exists():
        return parse_<tool_name>_json(json_path)
    return parse_<tool_name>_json_string(output)
```

---

## Step 5 — Chunk builder

`application/rag/chunks/<tool_name>.py` converts `ToolResult` objects into ChromaDB documents.
The class is found automatically by `ChunkBuilderFactory`: it scans the module for a class
whose `tool_name` attribute matches the tool name being ingested.

### Required class attributes

```python
from typing import Any
from domain.tools.base import ToolResult
from ._shared import _first_output_file, _shared_meta


class <ToolName>ChunkBuilder:

    # Must exactly match the wrapper's name property (and commands.json key)
    tool_name = "<tool-name>"

    # "code"    — SAST, SCA, secrets (most tools)
    # "web"     — API/DAST scanners (ZAP)
    # "network" — network/host scanners (nmap)
    domain = "code"

    # Fields the tool already provides, so the LLM enrichment pipeline skips them.
    # Available enrichment fields: severity, confidence, risk_type, remediation, description
    provided_fields: frozenset[str] = frozenset({"severity"})

    # Maps finding_type → set of type_* boolean flags that should be True.
    # All type_* flags not listed default to False.
    # Available flags: type_secret, type_vulnerability, type_weakness,
    #                  type_misconfiguration, type_exposure, type_dependency,
    #                  type_informational
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability"},
    }
```

#### `provided_fields` — what to put here

Include a field when the tool outputs it natively and it does not need LLM inference:

| Field | Include when… |
|---|---|
| `severity` | Tool outputs a severity level (critical/high/medium/low) |
| `confidence` | Tool outputs a confidence score (confirmed/probable/potential) |
| `risk_type` | Tool names the vulnerability class (e.g. gitleaks sets rule_id as risk_type) |
| `remediation` | Tool includes fix guidance |
| `description` | Tool includes a human-readable explanation |

When a field is in `provided_fields` the enrichment pipeline leaves it unchanged. When it
is absent the pipeline calls the LLM to generate a value. If your tool outputs severity
but the values aren't always reliable, omit `severity` from `provided_fields` and let the
LLM normalise it.

#### `type_flags` — what to put here

Each finding type maps to a set of boolean flags stored in the ChromaDB metadata. These
flags power `search --type=vulnerability` style filtering. The finding type you use as the
key (`"vulnerability"`, `"dependency"`, etc.) must match the `finding_type` value you set
in the metadata dict your `build()` method produces.

Common patterns:

```python
# SAST tool finding a code vulnerability
type_flags = {"vulnerability": {"type_vulnerability", "type_weakness"}}

# Dependency scanner
type_flags = {"dependency": {"type_dependency", "type_vulnerability"}}

# Secret scanner
type_flags = {"secret": {"type_secret"}}

# Network scanner (no boolean flags needed — just informational)
type_flags = {"informational": set()}
```

### Implementing `build()`

```python
import json
from datetime import UTC, datetime
from typing import Any

from domain.tools.base import ToolResult
from ._shared import _first_output_file, _shared_meta


class <ToolName>ChunkBuilder:
    tool_name = "<tool-name>"
    domain = "code"
    provided_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        parsed: dict[str, Any] = result.parsed_data or {}
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        source_file = _first_output_file(result.output_files)
        ts_compact = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        chunks: list[tuple[str, dict[str, Any], str]] = []

        for i, finding in enumerate(findings):
            # Build the text that gets embedded for semantic search
            text = (
                f"[{self.tool_name}] [{finding.get('severity', 'low').upper()}]"
                f" {finding.get('rule_id', '')} in {finding.get('file', '')}\n"
                f"{finding.get('message', '')}"
            )

            meta: dict[str, Any] = {
                "tool":         self.tool_name,
                "profile":      profile,
                # finding_type is stored as a JSON-encoded list for multi-type support
                "finding_type": json.dumps(["vulnerability"]),
                "severity":     finding.get("severity", "low"),
                "timestamp":    result.timestamp,
                "source_file":  source_file,
                # Add any tool-specific fields here
                "rule_id":      finding.get("rule_id", ""),
                "file_path":    finding.get("file", ""),
            }

            # _shared_meta adds: domain, enriched=False, and all type_* booleans.
            # Always call with self (not self.tool_name) — the signature changed in
            # the current codebase to read domain and type_flags from the builder instance.
            meta.update(_shared_meta(self, "vulnerability"))

            doc_id = f"{self.tool_name.replace('-', '_')}_{profile}_finding_{i}_{ts_compact}"
            chunks.append((text, meta, doc_id))

        return chunks

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        """Unique key used for deduplication. Must be stable across re-scans."""
        return "|".join([
            self.tool_name,
            str(finding.get("rule_id", "")),
            str(finding.get("file_path", "")),
            str(finding.get("line_start", "")),
        ])
```

Each `build()` call returns a list of `(text, metadata, doc_id)` tuples:

- **text** — the string that gets embedded. Include the tool name prefix `[toolname]` and
  the most semantically meaningful content. This is what the LLM sees during `chat`.
- **metadata** — a flat `dict[str, Any]`. ChromaDB only supports `str`, `int`, `float`,
  and `bool` values. Lists must be JSON-encoded to a string.
- **doc_id** — a stable unique string. Follow the convention
  `<tool_id>_<profile>_<type>_<index>_<timestamp>`.

### SCA shortcut

If your tool scans dependencies for known vulnerabilities (like pip-audit, npm-audit, or
osv-scanner) and your parser outputs `parsed_data["vulnerabilities"]` as a list with the
standard SCA fields, you can skip writing a full `build()` and delegate to the shared SCA
builder:

```python
from .sca import _build_sca_chunks, _sca_fingerprint_key


class GrypeChunkBuilder:
    tool_name = "grype"
    domain = "code"
    provided_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "dependency": {"type_dependency", "type_vulnerability"}
    }

    def build(self, result: ToolResult, profile: str) -> list[tuple[str, dict, str]]:
        return _build_sca_chunks(self, result, profile)

    def fingerprint_key(self, finding: dict) -> str:
        return _sca_fingerprint_key("grype", finding)
```

`_build_sca_chunks` expects each vulnerability in `parsed_data["vulnerabilities"]` to
contain these keys (all optional except `package_name`):

```
package_name, package_version, vulnerability_id, severity, summary,
affected_ecosystem, fixed_version, introduced_version, cvss_score, cvss_vector,
source_file, source_type, details, published, modified, references, cwe_ids, aliases
```

---

## Step 6 — Register in `commands.json`

The tool will not be instantiated until it has an entry in `config/commands.json`. Either
run `tool add` in the REPL (which auto-discovers your binary via `_candidate_commands`) or
write the entry manually:

**Local binary:**
```json
"<tool-name>": {
  "type": "repo",
  "location": "local",
  "path": "/usr/local/bin/<binary>"
}
```

Use `"type": "api"` instead of `"repo"` when `_command_entry_type = "api"` (ZAP-style
tools that scan HTTP targets, not filesystem paths).

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

## Step 7 — Verify

### Chunk builder is discovered

```bash
.venv/bin/python -c "
from application.rag.ingestor import _default_builders
builders = _default_builders()
print(sorted(builders.keys()))
assert '<tool-name>' in builders
print('chunk builder OK:', builders['<tool-name>'].domain)
"
```

### Wrapper is registered

```bash
.venv/bin/python -c "
from application.tools.registry import tool_registry, discover_tools
discover_tools('.')
t = tool_registry.get_tool('<tool-name>')
print('registered:', t)
print('available:', t.check_available())
print('segment:', t.scan_segment)
print('always_run:', t.always_run)
print('candidate_commands:', t._candidate_commands)
"
```

### Parse round-trip

```bash
.venv/bin/python -c "
from infrastructure.tools.parsers.<tool_name>_parser import parse_<tool_name>_json_string
result = parse_<tool_name>_json_string('<sample json output here>')
assert 'error' not in result, result
print(result.keys())
"
```

### Linter and type checker

```bash
.venv/bin/ruff check \
  infrastructure/tools/wrappers/base/<tool_name>.py \
  infrastructure/tools/wrappers/local/<tool_name>.py \
  application/rag/chunks/<tool_name>.py

.venv/bin/pyright \
  infrastructure/tools/wrappers/base/<tool_name>.py \
  infrastructure/tools/wrappers/local/<tool_name>.py \
  application/rag/chunks/<tool_name>.py
```

### Test suite

```bash
.venv/bin/python -m pytest --tb=short -q
```

The test suite should still pass with zero failures. If you write ingestion tests (see
`tests/ingest/test_pip_audit.py` for the pattern), add them under `tests/ingest/`.

---

## Common mistakes

**Missing `always_run` or `candidate_commands` on the base class**

Both properties are abstract on `ToolInterface`. If your base class omits either one,
Python raises `TypeError: Can't instantiate abstract class` the moment tally tries to
register the wrapper. Every base class must implement both.

**Wrong `_shared_meta` call signature**

```python
# Wrong — pre-Plan 011 signature
meta.update(_shared_meta("mytool", "vulnerability"))

# Correct — pass the builder instance
meta.update(_shared_meta(self, "vulnerability"))
```

**Wrong `_build_sca_chunks` call signature**

```python
# Wrong
return _build_sca_chunks("grype", result, profile)

# Correct
return _build_sca_chunks(self, result, profile)
```

**`tool_name` mismatch between wrapper and chunk builder**

`ChunkBuilderFactory.load("npm-audit")` imports `application.rag.chunks.npm_audit` and then
looks for a class with `tool_name == "npm-audit"`. If your chunk builder's `tool_name`
attribute is `"npm_audit"` (underscores) the factory returns `None` and findings are
silently not ingested.

**File name uses hyphens**

Python module names cannot contain hyphens. The file must be `npm_audit.py`, not
`npm-audit.py`. The discovery code converts underscores back to hyphens to produce the
tool name.

**`metadata` value is a list**

ChromaDB does not accept list values in metadata. If you have a list field (e.g.
`aliases`, `cwe_ids`, `tags`), join it to a comma-separated string:

```python
if aliases:
    meta["aliases"] = ", ".join(aliases)
```

**Multiple ExecutionPasses but `merge_pass_results` returns only the first**

If your tool needs multiple passes (running the binary twice with different arguments)
you must implement `merge_pass_results` to combine them. The default implementation
returns `pass_results[0]`, which silently drops all subsequent pass results.

**`findings_exit_ok` is False for a tool that exits 1 on findings**

When `findings_exit_ok=False` and the binary exits 1 (which most security scanners do
when they find something), tally marks `result.success = False` and the findings are not
ingested. Check your tool's exit code behaviour and set this accordingly.
