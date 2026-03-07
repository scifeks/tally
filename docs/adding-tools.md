# Adding Tool Wrappers to Tally

Tally uses an auto-discovery system for tool wrappers. To add a new tool, create a single Python file in `core/tools/wrappers/`. No registry changes, no imports to update — the file is discovered and registered on the next startup.

---

## Step 1: Create the Wrapper File

Create `core/tools/wrappers/mytool.py`. The filename becomes the module name but the tool's identity is determined by the `name` property you implement.

---

## Step 2: Implement the ToolWrapper Interface

Your class must subclass `ToolWrapper` from `core.tools.base` and implement all abstract properties and methods.

```python
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ToolWrapper


class MyToolWrapper(ToolWrapper):

    @property
    def name(self) -> str:
        """The tool's canonical name used in REPL commands and the registry.
        Example: 'mytool' means users run 'scan -t mytool'."""
        return "mytool"

    @property
    def command(self) -> str:
        """The binary name looked up on PATH.
        Used by check_available() and get_version()."""
        return "mytool"

    @property
    def category(self) -> str:
        """Functional category: 'network', 'sast', 'sca', 'secrets', 'api'.
        Determines which scan segment this tool belongs to."""
        return "sast"

    @property
    def scope(self) -> str:
        """Scope of the scan: 'project' (runs once) or 'repository' (runs per repo)."""
        return "repository"

    @property
    def description(self) -> str:
        """One-line description shown in help output."""
        return "My tool for finding vulnerabilities"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        """Optional list of language strings this tool supports.
        Return None to indicate no language restriction.
        Example: ['python', 'javascript']"""
        return None

    def check_available(self) -> bool:
        """Return True if the tool binary is present on PATH.
        Tally calls this on startup and before every scan.
        Tools that return False are skipped with a 'NOT INSTALLED' message."""
        return shutil.which("mytool") is not None

    def build_command(self, **kwargs) -> List[str]:
        """Return the full argv list for this tool invocation.

        Tally passes kwargs from the orchestrator. Common kwargs:
          repo_path (str)    — path to the repository being scanned
          label (str)        — profile or repo name (used for output filenames)
          cwd (str)          — working directory for execution

        Raise ValueError for missing required kwargs.
        """
        repo_path = kwargs.get("repo_path")
        if not repo_path:
            raise ValueError("repo_path is required for mytool")

        return ["mytool", "--output-format", "json", repo_path]

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        """Parse raw tool output into a structured dict for ingestion into RAG.

        Args:
            output: Raw stdout captured from the tool.
            files:  Dict mapping label strings to saved output file paths.
                    'stdout' key typically contains the path to saved stdout.

        Return a dict. The dict is stored as-is in parsed_data on ToolResult.
        An 'error' key at the top level signals a failed parse to the orchestrator.
        """
        stdout_path = files.get("stdout")
        if stdout_path and stdout_path.exists():
            raw = stdout_path.read_text()
        else:
            raw = output

        try:
            import json
            data = json.loads(raw)
            findings = data.get("results", [])
            return {
                "findings": findings,
                "summary": {"total_findings": len(findings)},
            }
        except Exception as exc:
            return {"error": str(exc), "raw": raw[:500]}
```

---

## The ToolResult Dataclass

The executor populates `ToolResult` after running your tool. You do not create it directly — your `parse_output()` method returns the dict that becomes `parsed_data`.

```python
@dataclass
class ToolResult:
    tool_name: str          # From tool.name
    success: bool           # True if exit code 0 (or normalized by orchestrator)
    output: str             # Raw stdout+stderr string
    parsed_data: dict       # Return value of parse_output()
    output_files: dict      # Paths to saved stdout/stderr files
    timestamp: str          # ISO 8601 UTC timestamp
    duration_seconds: float # Wall-clock execution time
```

---

## How Auto-Discovery Works

When Tally starts, `core/tools/registry.py` scans `core/tools/wrappers/` for `.py` files (excluding `__init__.py` and any file starting with `_`). For each file, it imports the module and registers any class that:

1. Is a subclass of `ToolWrapper`
2. Is defined in that module (not imported from elsewhere)
3. Is not `ToolWrapper` itself

Your class is instantiated with no arguments and `register()` is called automatically. This means:

- **No changes to `__init__.py` or the registry are needed**
- **File name does not need to match the tool name**
- **Multiple wrapper classes in one file are all registered**

To add your tool to a scan segment, add it to `SCAN_SEGMENTS` in `core/tools/orchestrator.py`:

```python
SCAN_SEGMENTS: Dict[str, List[str]] = {
    'network': ['nmap'],
    'sast': ['semgrep', 'mytool'],   # Add here
    ...
}
```

To include it in `repo-scan`, add it to `ALWAYS_RUN_REPO_TOOLS` or `LANGUAGE_TOOL_MAP` in the same file.

---

## RAG Ingestion and Metadata

After a successful scan, `FindingIngestor` converts the findings in `parsed_data` into documents stored in ChromaDB. Each document gets a metadata dict that drives search, filtering, and reports.

### Common Metadata Fields

These fields are used across all tools:

| Field | Type | Description |
|---|---|---|
| `tool` | string | Tool name (from `ToolResult.tool_name`) |
| `profile` | string | Profile or repo name passed during ingestion |
| `finding_type` | string | Type of finding (e.g. `open_port`, `vulnerability`, `secret`) |
| `severity` | string | Severity level: `critical`, `high`, `medium`, `low` |
| `timestamp` | string | ISO 8601 timestamp of the scan |

### Tool-Specific Metadata Examples

The ingestor maps fields from `parsed_data` to metadata. Reviewing `core/rag/ingestor.py` shows the exact mapping for each tool. Common patterns:

- **Semgrep:** `rule_id`, `file_path`, `line_start`, `cwe`
- **SCA tools:** `package_name`, `package_version`, `vulnerability_id`, `fixed_version`
- **Gitleaks:** `rule_id`, `file_path`, `line_number` (secret value is never stored)
- **nmap:** `ip_address`, `port`, `service`
- **ZAP:** `alert_name`, `url`, `method`, `param`, `cwe_id`

Structure your `parse_output()` return value with a `findings` list where each finding dict contains the fields your ingestor mapping expects.

---

## Docker Wrappers

Every tool that can run locally should also have a Docker wrapper so users can run it inside a container. Local wrappers live in `core/tools/wrappers/local/`; Docker wrappers live in `core/tools/wrappers/docker/`.

### Base Class

Docker wrappers subclass `DockerToolWrapper` from `core.tools.base` instead of `ToolWrapper`. `DockerToolWrapper` extends `ToolWrapper` with:

- `__init__(self, config)` — receives the `CommandEntry` from `commands.json` and stores `container.name` and `container.tool_path`
- `container_name` / `tool_path` properties — expose the configured container details
- `command` property — always returns `"docker"` (the host-side binary used)
- `check_available()` — always returns `True`; presence in `commands.json` means the user configured it
- `get_version()` — always returns `None`
- `_build_docker_exec(tool_args, workdir=None)` — helper that builds the full `["docker", "exec", ...]` argv list

### What to Implement

Your Docker wrapper must implement: `name`, `category`, `scope`, `description`, `build_command`, and `parse_output`. You do **not** implement `command`, `check_available`, or `get_version` — those are handled by the base class.

In `build_command`, call `self._build_docker_exec(tool_args)` to produce the final argv rather than building the docker prefix by hand:

```python
from ...base import DockerToolWrapper

class DockerMyToolWrapper(DockerToolWrapper):

    @property
    def name(self) -> str:
        return "mytool"

    @property
    def category(self) -> str:
        return "sast"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return "My tool for finding vulnerabilities"

    def build_command(self, **kwargs) -> list:
        repo_path = kwargs.get("repo_path", "")
        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this repository. "
                "Use 'repo edit' to set the container mount path."
            )
        tool_args = ["--output-format", "json", repo_path]
        return self._build_docker_exec(tool_args)

    def parse_output(self, output, files):
        # identical to the local wrapper's parse_output
        ...
```

The generated command looks like:

```
docker exec <container_name> /usr/local/bin/mytool --output-format json /repo
```

With `workdir` set it becomes:

```
docker exec -w /repo <container_name> /usr/local/bin/mytool --output-format json .
```

### File Location

```
core/tools/wrappers/
  local/mytool.py      ← local wrapper (subclasses ToolWrapper)
  docker/mytool.py     ← docker wrapper (subclasses DockerToolWrapper)
```

The registry discovers both automatically — no imports or registry changes needed. The wrapper that gets instantiated depends on which `location` is set in `commands.json` for that tool.

---

## Developer Checklist

Use this checklist to verify your wrapper is working before committing:

- [ ] **Local wrapper created** at `core/tools/wrappers/local/mytool.py` (subclasses `ToolWrapper`)

- [ ] **Docker wrapper created** at `core/tools/wrappers/docker/mytool.py` (subclasses `DockerToolWrapper`)

- [ ] **check_available() returns correct value** (local wrapper)
  ```bash
  .venv/bin/python3 -c "
  from core.tools import tool_registry
  t = tool_registry.get_tool('mytool')
  print('available:', t.check_available())
  "
  ```

- [ ] **Tool appears in startup discovery table**
  ```bash
  .venv/bin/python3 tally.py --skip-checks
  # Look for 'mytool' in the [*] Discovering tools... output
  ```

- [ ] **build_command() produces correct CLI args**
  ```bash
  .venv/bin/python3 -c "
  from core.tools import tool_registry
  t = tool_registry.get_tool('mytool')
  print(t.build_command(repo_path='/tmp/test'))
  "
  ```

- [ ] **parse_output() returns expected structure**
  ```bash
  .venv/bin/python3 -c "
  from core.tools import tool_registry
  from pathlib import Path
  t = tool_registry.get_tool('mytool')
  result = t.parse_output('{\"results\": []}', {})
  print(result)
  assert 'error' not in result
  print('parse_output OK')
  "
  ```

- [ ] **scan mytool runs without errors** (requires a project and the tool installed)
  ```
  [myproject]> scan mytool
  ```

- [ ] **get_version() returns a string or None** (not an exception; N/A for Docker wrappers)
  ```bash
  .venv/bin/python3 -c "
  from core.tools import tool_registry
  t = tool_registry.get_tool('mytool')
  print('version:', t.get_version())
  "
  ```
