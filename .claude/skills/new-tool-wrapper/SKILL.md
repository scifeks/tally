---
name: new-tool-wrapper
description: Guides creation of a new security tool integration for tally. Invoke
  when the user asks to add a new tool, write a new tool wrapper, or integrate
  a new security scanner.
---

# New Tool Wrapper Skill

Adding a new tool requires up to four source files, a `commands.json` entry, and
a documentation update:

1. `infrastructure/tools/wrappers/base/<tool_name>.py` - base class (local + docker share it)
2. `infrastructure/tools/wrappers/local/<tool_name>.py` - concrete local wrapper
3. `infrastructure/tools/wrappers/docker/<tool_name>.py` - concrete docker wrapper (if needed)
4. `infrastructure/tools/parsers/<tool_name>.py` - parser functions + ToolHandler in one file
5. `config/commands.json` entry (or `tool add` in the REPL)
6. `docs/tools.md` - add a row to the Supported Tools table

**No edits to any other existing source file** unless noted below.

---

## Step 1: Interview

Ask these questions **in a single message** before writing code.
Skip any whose answers are obvious from context.

```
1. Tool name (kebab-case, e.g. "trivy", "trufflehog", "grype")
2. Location: local, docker, or both?
3. Binary name(s) for shutil.which / candidate_commands
   - If docker: container name pattern
4. Scan segment:
      sast    -> static analysis
      sca     -> dependency / supply chain
      secrets -> secret detection
      web     -> web/API/DAST scanning
      llm     -> LLM security testing
5. Does it exit non-zero when findings are present? (findings_exit_ok)
6. Language gates (empty = all repos; or python / javascript / php / etc.)
7. always_run: True (run on every scan) or False (only when language matches)?
8. skip: False for most tools; True if findings never reach triage
9. requires_base_urls: True for DAST scanners that need repo.base_urls
10. What does a single finding look like? (key fields the tool outputs)
11. Finding type(s): secret / vulnerability / weakness / dependency / informational
12. Which fields does the tool provide natively (no LLM enrichment needed)?
    Choose from: severity, confidence, risk_type, remediation, description
13. Output format: JSON, XML, other?
    If JSON: top-level structure (e.g. {"results": [...]})
14. Invocation pattern (e.g. trivy fs <repo_path> --format json)
    For docker: docker exec pattern
15. Is this SCA-style (dep vulnerabilities)? If yes, does parsed output use the
    vulnerabilities list (package_name, vulnerability_id, severity, etc.)?
16. Should findings appear in the web UI? (should_visualize)
    False for discovery/metadata tools like Noir and Katana.
17. Is this a discovery tool (finds endpoints, not vulnerabilities)?
    If yes: is_discovery_tool=True, skip=True, should_visualize=False.
18. Handler domain: code, web, or llm?
    - code: SAST, SCA, secrets tools
    - web: DAST, crawlers, web scanners
    - llm: LLM-specific security scanners
19. Does the tool write output to a separate file or stdout?
    If separate file: local wrapper must override parse_output.
20. Does the local wrapper need precondition checks before running?
    (e.g. lockfile generation for SCA, seed file for DAST)
```

Wait for all answers before writing code.

---

## Step 2: Choose implementation strategy

- **SCA-style**: delegate to `_build_sca_normalize` / `_sca_render` /
  `_sca_fingerprint_key` from `infrastructure/tools/parsers/_sca_shared.py`.
  See `pip_audit.py` for a ~30-line reference.
- **Custom findings**: write a full handler. See `semgrep.py` or `gitleaks.py`
  in `infrastructure/tools/parsers/`.
- **Discovery tool**: set `is_discovery_tool=True`, `skip=True`,
  `should_visualize=False`. See `katana.py` or `noir.py` for reference.
- **Custom timeout**: override `timeout` property in the base class
  (e.g. Katana returns 1200 for long crawls).

### Pre-run utilities

Tools that need setup before scanning can use shared helpers from
`infrastructure/tools/wrappers/utils/`:

- `install_fallback.ensure_lockfile(tool_name, repo_path, lockfile_name, install_cmd)` -
  generates lockfiles for SCA tools (npm, pip, composer) if missing.
- `scope.scope_key(url)` - normalizes URLs to `(hostname, port)` tuples for
  URL-based scope enforcement in crawlers/DAST tools.

### Enrichment configuration

Use interview answers Q10-Q12 to decide how enrichment works for this tool.

**Available enrichment fields** (defined in `domain/tools/constants.py`):
`risk_type`, `remediation`, `severity`, `confidence`, `description`,
`owasp_name`, `title`.

**Decision flow:**

1. If the tool's findings don't benefit from LLM enrichment (e.g. secret
   detectors where rule_id IS the risk_type):
   set `should_enrich = False`, `enrichment_fields = None`.
   Put any fields the tool provides natively in `non_enriched_fields`.

2. If the tool needs LLM enrichment for some fields:
   set `should_enrich = True`.
   Put natively-provided fields in `non_enriched_fields` (these are NOT
   overwritten by the LLM). Build `enrichment_fields` as a tuple of
   `FieldEnrichmentSpec` for each field the LLM should infer.

**`FieldEnrichmentSpec` fields** (from `domain/tools/enrichment.py`):
- `field_name`: one of the enrichment field keys above.
- `source_fields`: tuple of keys from the normalized row dict, listed in
  priority order. These are the seed data the LLM sees when inferring the
  field. Keys absent from a finding are silently skipped.
- `strategy`: `PromptStrategy.GENERIC` for open-ended fields (risk_type,
  remediation, confidence, title, description, severity).
  `PromptStrategy.DEDICATED` for constrained fields that must match an
  exact enum value (`owasp_name`).

**SCA tools**: use `_SCA_COMMON_ENRICHMENT_FIELDS` (pip-audit, npm-audit,
composer-audit) or `_SCA_OSV_ENRICHMENT_FIELDS` (osv-scanner, richer
metadata) from `_sca_shared.py`.

---

## Step 3: Base class

`infrastructure/tools/wrappers/base/<tool_name>.py`

The base class inherits from `ToolInterface` only. It also implements the
`ToolWrapper` protocol properties (`category`, `scope`, `description`,
`supported_languages`) but does NOT inherit from `ToolWrapper` directly.

```python
"""Shared base class for <tool> local and docker wrappers."""

from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.interface import ToolInterface
from infrastructure.tools.parsers.<tool_name> import (
    parse_<tool_name>_json,
    parse_<tool_name>_json_string,
)


class Base<ToolName>Tool(ToolInterface):
    _candidate_commands: list[str] = ["<binary>"]
    _command_entry_type: str = "repo"   # or "api" for URL-targeted tools

    @property
    def name(self) -> str:
        return "<tool-name>"   # kebab-case

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
        return "<segment>"

    @property
    def skip(self) -> bool:
        return False

    @property
    def should_visualize(self) -> bool:
        return True

    @property
    def findings_exit_ok(self) -> bool:
        return True

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def always_run(self) -> bool:
        return True

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_<tool_name>_json(json_path)
        return parse_<tool_name>_json_string(output)

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        summary = parsed_data.get("summary", {})
        return summary.get("total_findings", len(parsed_data.get("findings", [])))
```

### Abstract members on `ToolInterface` (all required)

`name`, `scan_segment`, `findings_exit_ok`, `language_gates`,
`requires_base_urls`, `always_run`, `candidate_commands`, `skip`,
`should_visualize`, `build_execution_passes`, `merge_pass_results`,
`count_findings`.

Missing any raises `TypeError` at instantiation.

### Optional overrides (have defaults on `ToolInterface`)

- `is_discovery_tool` - default `False`. Override to `True` for endpoint
  discovery tools (Noir, Katana). Discovery tools run before scanners in
  the same segment.
- `timeout` - default `None` (uses executor's default). Override with an
  int (seconds) for tools that routinely need more time.
- `display_fields` - default `[]`. Rarely needed.

### Note on `build_execution_passes`

The base class does NOT implement `build_execution_passes`. This method is
abstract on `ToolInterface` and must be implemented by the local and/or
docker wrappers, because it requires registry path resolution and
execution-mode-specific precondition checks.

---

## Step 4: Local wrapper

`infrastructure/tools/wrappers/local/<tool_name>.py`

Inherits only from the base class. Must implement `build_execution_passes`,
`build_command`, `command`, `check_available`, and `get_version`.

Override `parse_output` only if the tool writes to a separate file rather
than stdout (gitleaks pattern).

```python
"""<tool> local wrapper."""

import shutil
from pathlib import Path

from domain.tools.interface import ExecutionContext, ExecutionPass
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
            raise ValueError("repo_path is required for <tool>")
        if not Path(repo_path).exists():
            raise ValueError(f"Repository path does not exist: {repo_path!r}")
        return [self.command, "<args>", repo_path]

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
            )
        ]
```

### Common local wrapper patterns

**Graceful skip when preconditions are missing** (return empty list):

```python
def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
    assert context.repo is not None
    repo_path = context.registry.get_repo_path(self.name, context.repo)

    if not (Path(repo_path) / "package.json").exists():
        return []

    return [
        ExecutionPass(
            label_suffix=context.repo.name,
            kwargs={"repo_path": repo_path},
            cwd=repo_path,  # when the tool must run inside the repo
        )
    ]
```

**SCA lockfile generation** (from `wrappers/utils/install_fallback.py`):

```python
from infrastructure.tools.wrappers.utils.install_fallback import ensure_lockfile

def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
    assert context.repo is not None
    repo_path = context.registry.get_repo_path(self.name, context.repo)

    if not ensure_lockfile(
        "npm-audit", repo_path, "package-lock.json",
        ["npm", "install", "--package-lock-only"],
    ):
        return []

    return [
        ExecutionPass(
            label_suffix=context.repo.name,
            kwargs={"repo_path": repo_path},
            cwd=repo_path,
        )
    ]
```

**Configurable binary path** (from config):

```python
def __init__(self, config=None) -> None:
    self._binary = (config.path if config and config.path else "tool-name")

@property
def command(self) -> str:
    return self._binary
```

---

## Step 5: Docker wrapper

`infrastructure/tools/wrappers/docker/<tool_name>.py`

Also inherits only from the base class. `parse_output` is inherited.

```python
"""<tool> docker wrapper."""

from domain.tools.interface import ExecutionContext, ExecutionPass
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
                "Use 'edit-repo' to set the container mount path."
            )
        tool_args = ["<args>", repo_path]
        return build_docker_exec(self._container_name, self._tool_path, tool_args)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={"repo_path": repo_path},
            )
        ]
```

`build_docker_exec(container_name, tool_path, tool_args, workdir=None)` builds:
`["docker", "exec", "-w", workdir, container_name, tool_path, *tool_args]`
(omits `-w` when `workdir` is None).

### Docker `check_available` variants

For tools where availability depends on the binary existing inside the
container, use `docker exec` to verify:

```python
import subprocess

def check_available(self) -> bool:
    try:
        result = subprocess.run(
            ["docker", "exec", self._container_name, "test", "-f", self._tool_path],
            capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False
```

---

## Step 6: Parser + Handler

`infrastructure/tools/parsers/<tool_name>.py` is **one file** for both.

`ToolHandlerFactory.load(tool_name)` imports this module and finds the handler class
by matching the `tool_name` class attribute.

```python
"""Parser and handler for <tool> output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult

from ._shared import _first_output_file, _shared_meta


# ---------------------------------------------------------------------------
# Parser
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
    tool_name = "<tool-name>"   # must match wrapper name property exactly
    domain = "code"             # "code", "web", or "llm"
    segment = "<segment>"       # matches scan_segment on the wrapper
    non_enriched_fields: frozenset[str] = frozenset({"severity"})
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability"},
    }
    should_enrich = True
    should_visualize = True
    enrichment_fields = None    # see enrichment variant below

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

**SCA shortcut**: if parser outputs `"vulnerabilities"` with standard SCA fields:

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

**Enrichment-enabled variant**: when the tool needs LLM enrichment for
specific fields, declare `enrichment_fields` as a tuple of specs. Each
spec tells the enrichment pipeline which normalized row keys to send as
seed context and which prompt strategy to use.

```python
from domain.tools.base import ToolResult
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta


class <ToolName>Handler:
    tool_name = "<tool-name>"
    domain = "web"
    segment = "web"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset(
        {"severity", "confidence"}
    )
    type_flags: dict[str, set[str]] = {
        "vulnerability": {"type_vulnerability"},
    }
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "owasp_name",
            ("risk_type", "param", "payload", "url"),
            PromptStrategy.DEDICATED,
        ),
        FieldEnrichmentSpec(
            "title",
            ("risk_type", "url", "param"),
            PromptStrategy.GENERIC,
        ),
    )
    normalized_fields: list[str] = [
        "confidence",
        "finding_type",
        "severity",
        "url",
    ]

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        ...  # same structure as base template

    def render(self, row: dict) -> str:
        ...

    def fingerprint_key(self, finding: dict) -> str:
        ...
```

The `source_fields` tuple in each spec must reference keys that
`normalize()` puts into the row dict. If a key is never set, the LLM
gets less context than intended (the key is silently skipped).

---

## Step 7: Documentation

After the code is written, update `docs/tools.md` to register the new tool.

### Required: Supported Tools table

Add a row to the `## Supported Tools` table at the top of `docs/tools.md`:

```markdown
| <Tool Name> | <Category> | <One-line description> |
```

Category is one of: SAST, SCA, DAST, Pre-DAST, Secrets. Match the existing
table style (tool name as displayed, not kebab-case).

### Conditional: tool-specific section

Add a dedicated H2 or H3 section in `docs/tools.md` if any of the following apply:

- The tool has **configuration requirements** beyond install-and-scan (e.g.
  pip-audit's `dependencies_file`, XSStrike's URL seed mode)
- The tool has **known limitations** or skip conditions that users should
  know about (e.g. Noir's Node.js limitation)
- The tool has **special dependencies** that are not obvious (e.g. FuzzyWuzzy
  for XSStrike)
- The tool interacts with **other tools** in the pipeline (e.g. Noir feeding
  endpoints to ZAP)

If none of these apply, the table row is sufficient. Do not add a section
that restates the table row in prose.

### Conditional: other docs

If the new tool introduces behavior that affects other documented features,
update those docs too:

| Scenario | Also update |
|---|---|
| New SCA tool with language-specific `dependencies_file` behavior | `docs/tools.md` pip-audit section (add similar detail) |
| New DAST tool that consumes merged endpoint URLs | `docs/url-discovery.md` downstream consumers table |
| New tool that requires Docker containers | `docs/docker.md` if containers are provided |
| New pre-DAST tool that feeds into ZAP or other scanners | `docs/url-discovery.md` and `docs/tools.md` |

---

## Step 8: Verification checklist

After writing all files, verify:

1. Add the tool to `config/commands.json` (or use `tool add` in the REPL):
   ```json
   "<tool-name>": { "type": "repo", "location": "local", "path": "/path/to/binary" }
   ```

2. Verify handler auto-discovery:
   ```
   .venv/bin/python -c "from application.rag.ingestor import ToolHandlerFactory; h = ToolHandlerFactory.load('<tool-name>'); print(h)"
   ```

3. Run the linter and type checker on the new files:
   ```
   .venv/bin/ruff check infrastructure/tools/wrappers/base/<tool_name>.py infrastructure/tools/wrappers/local/<tool_name>.py infrastructure/tools/parsers/<tool_name>.py
   .venv/bin/pyright infrastructure/tools/wrappers/base/<tool_name>.py infrastructure/tools/wrappers/local/<tool_name>.py infrastructure/tools/parsers/<tool_name>.py
   ```

4. Run the test suite:
   ```
   .venv/bin/pytest tests/unit/ -q --tb=short
   ```

5. Verify `docs/tools.md` has the new row in the Supported Tools table.

---

## Common mistakes to avoid

- **Wrong import paths.** Use `domain.tools.base` / `domain.tools.interface`,
  NOT `core.tools.*`. Use absolute imports, never cross-layer relative imports.
- **`skip` not implemented.** Abstract on `ToolInterface`; missing raises `TypeError`.
- **`should_visualize` not implemented.** Abstract on `ToolInterface`; missing
  raises `TypeError`. Most tools return `True`; discovery tools return `False`.
- **`tool_name` mismatch.** Handler `tool_name` must exactly match the wrapper `name`.
  Underscore vs hyphen mismatch causes silent ingestion failure.
- **`fingerprint_key` missing.** Every handler must implement it. Omitting causes
  duplicate findings on re-scans.
- **Inheriting `ToolWrapper` directly.** Base classes inherit from `ToolInterface`
  only. They implement `ToolWrapper` properties (`category`, `scope`, `description`,
  `command`) as concrete methods without inheriting from the `ToolWrapper` ABC.
- **`build_command` positional args.** Must be `def build_command(self, **kwargs)`.
  Extract `repo_path` from `kwargs`.
- **`build_execution_passes` in base class only.** The local/docker wrappers must
  implement this method. It requires registry path resolution and precondition
  checks that are execution-mode-specific.
- **`parse_output` duplicated.** Put it in the base class. Only override in
  local/docker when the tool writes to a separate file (gitleaks pattern).
- **File stem with hyphens.** Filename must be `npm_audit.py`, not `npm-audit.py`.
- **`_shared_meta(self.tool_name, ...)` instead of `_shared_meta(self, ...)`.**
  Signature takes the handler instance, not a string.
- **List in metadata.** ChromaDB rejects lists. Join to comma-separated string.
- **Forgetting docs/tools.md.** The tool is not discoverable to users until it
  appears in the Supported Tools table.
- **`source_fields` referencing keys not in normalized output.** Every key in
  a `FieldEnrichmentSpec.source_fields` tuple must be a key that `normalize()`
  actually sets on the row dict. Missing keys are silently skipped, so the LLM
  gets less context than intended.
- **`should_enrich = True` with `enrichment_fields = None`.** This combination
  falls through to a legacy batch path. Set `enrichment_fields` to a tuple of
  `FieldEnrichmentSpec` when `should_enrich` is `True`.
- **`scan_segment` set to `'api'`.** Not a valid segment. Valid segments are:
  `sast`, `sca`, `secrets`, `web`, `llm`.
- **Discovery tools without `skip=True`.** Tools with `is_discovery_tool=True`
  should also set `skip=True` and `should_visualize=False` since they produce
  endpoint metadata, not triage-able findings.
