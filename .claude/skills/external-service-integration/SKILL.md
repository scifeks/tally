---
name: external-service-integration
description: Use when adding an outbound integration to an external platform (e.g.,
  exporting findings to a vulnerability management system, SIEM, or ticketing tool).
  Invoke when the user asks to push data to an external service, add an export
  integration, or wire up automated sync to a third-party API.
---

# External Service Integration

Adding an outbound integration requires these files:

1. `core/config/schemas/<service>_config.py` - config schema (global + project override)
2. `application/ports/export.py` - reuse `ExportPort` or define a new port
3. `infrastructure/export/<service>/client.py` - thin HTTP wrapper
4. `infrastructure/export/<service>/mapper.py` - domain-to-wire format conversion
5. `infrastructure/export/<service>/adapter.py` - implements the port
6. `factories/export.py` - factory function for DI wiring
7. `application/sync/integration_sync.py` - register in sync dispatcher

---

## Step 1: Interview

Ask these questions **in a single message** before writing code.
Skip any whose answers are obvious from context.

```
1. Service name (lowercase, e.g. "defectdojo", "jira", "splunk")
2. API documentation URL
3. Authentication method: API key header, OAuth2, basic auth?
4. What data flows out?
   - Findings only
   - Findings + endpoints/URLs
   - Scan metadata
5. Wire format: JSON body, multipart form, XML?
6. Does the API support idempotent re-import (upsert) or append-only?
7. Per-project config overrides needed? (e.g., target project/workspace per tally project)
8. Trigger model:
   - Auto-sync after scan (post_scan_sync)
   - Auto-sync after triage (post_triage_sync)
   - On-demand export (REPL command / API route)
   - Combination
9. Error recovery: retry transient failures or fail-fast?
10. Does the service need context creation before import?
    (e.g., DefectDojo auto-creates products/engagements)
11. Rate limits or batch size constraints?
12. Connection test endpoint (e.g., GET /api/me, GET /health)
```

Wait for all answers before writing code.

---

## Step 2: Config Schema

Create `core/config/schemas/<service>_config.py`:

```python
from pydantic import BaseModel, ConfigDict, Field


class <Service>GlobalConfig(BaseModel):
    """<Service> server connection and defaults."""

    url: str
    api_token: str
    verify_ssl: bool = Field(default=True)
    # Add service-specific defaults here


class <Service>ProjectConfig(BaseModel):
    """<Service> project-level overrides."""

    model_config = ConfigDict(extra="ignore")

    # Fields that vary per tally project (e.g., target workspace)
```

Wire into `GlobalConfig` in `core/config/schemas/global_config.py`:

```python
<service>: <Service>GlobalConfig | None = None
```

Wire into `ProjectConfig` in `core/config/schemas/project_config.py` if project
overrides are needed.

---

## Step 3: Port Interface

If the integration exports findings, reuse `ExportPort` from
`application/ports/export.py`:

```python
class ExportPort(Protocol):
    def export_findings(self, findings: list[Finding]) -> ExportResult: ...
    def test_connection(self) -> bool: ...
```

If the data shape differs significantly (not findings), define a new port in
`application/ports/<service>.py` following the same pattern: an export method
returning a frozen result dataclass, plus `test_connection`.

---

## Step 4: HTTP Client

Create `infrastructure/export/<service>/client.py`:

```python
import httpx

_DEFAULT_TIMEOUT = 30.0


class <Service>Client:
    def __init__(
        self, url: str, api_token: str, *, verify_ssl: bool = True
    ) -> None:
        self._base_url = url.rstrip("/")
        self._headers = {"Authorization": "Token " + api_token}
        self._verify_ssl = verify_ssl

    def test_connection(self) -> bool:
        try:
            r = httpx.get(
                f"{self._base_url}/<health_endpoint>",
                headers=self._headers,
                verify=self._verify_ssl,
                timeout=_DEFAULT_TIMEOUT,
            )
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def post_findings(self, payload: bytes, **params) -> tuple[int, dict]:
        r = httpx.post(
            f"{self._base_url}/<import_endpoint>",
            headers=self._headers,
            content=payload,
            verify=self._verify_ssl,
            timeout=_DEFAULT_TIMEOUT,
        )
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text}
        return r.status_code, body
```

Rules for the client:
- No business logic. Returns `(status_code, body)` only.
- Auth header injected in `__init__`, not per-request.
- `verify_ssl` honored on every request.
- Timeouts explicit on every call (no global default).

---

## Step 5: Mapper

Create `infrastructure/export/<service>/mapper.py`:

```python
from domain.findings.entry import Finding


def map_findings(findings: list[Finding]) -> list[dict]:
    mapped = []
    for f in findings:
        try:
            mapped.append(_map_one(f))
        except Exception:
            log.warning("skipping unmappable finding %s", f.fingerprint)
    return mapped


def _map_one(f: Finding) -> dict:
    base = {
        # Map Finding fields to service format.
        # Use f.meta dict for tool-specific fields.
    }
    tool_mapper = _TOOL_MAPPERS.get(f.tool)
    if tool_mapper:
        base.update(tool_mapper(f))
    return base


_TOOL_MAPPERS: dict[str, Callable[[Finding], dict]] = {
    "semgrep": _map_semgrep,
    "gitleaks": _map_gitleaks,
    # Add per-tool mappers as needed
}
```

Rules for the mapper:
- Never raise on a single finding failure. Log and skip.
- Base mapping handles all tools. Per-tool mappers add extras only.
- Map severity strings explicitly (don't assume case matches).
- Handle None/missing fields with sensible defaults.
- Date fields: use ISO 8601 format, convert from `first_seen`.

---

## Step 6: Adapter

Create `infrastructure/export/<service>/adapter.py`:

```python
from application.ports.export import ExportPort, ExportResult


class <Service>ExportAdapter:
    def __init__(self, config, repo_names, project_name, ...):
        self._config = config
        self._client = <Service>Client(
            url=config.url,
            api_token=config.api_token,
            verify_ssl=config.verify_ssl,
        )
        # Store context needed for grouping/routing

    def export_findings(self, findings: list[Finding]) -> ExportResult:
        # 1. Group findings by relevant dimension (repo, tool, etc.)
        # 2. For each group: map, serialize, send via client
        # 3. On 401/403: stop immediately, return error result
        # 4. Aggregate counts into ExportResult
        ...

    def test_connection(self) -> bool:
        return self._client.test_connection()
```

Rules for the adapter:
- Group findings before sending (avoid one HTTP call per finding).
- Short-circuit on auth errors (don't retry 401/403).
- Aggregate partial results: some groups may succeed while others fail.
- Never log the API token value.

---

## Step 7: Factory & Composition

Add a factory function in `factories/export.py` (or a new file if the
integration has complex wiring):

```python
def build_<service>_export_service(
    config: <Service>GlobalConfig,
    finding_repo: FindingRepositoryPort,
    project_name: str,
    run_id: int | None = None,
    # ... other resolved dependencies
) -> ExportService:
    adapter = <Service>ExportAdapter(config=config, ...)
    return ExportService(finding_repo, adapter, run_id=run_id)


def create_<service>_export_for_project(
    base_path: str | Path,
    project_name: str,
    run_id: int | None = None,
) -> ExportService:
    config_manager = ConfigManager(str(base_path))
    global_config = config_manager.load_global_config()
    svc_config = global_config.<service>
    if svc_config is None:
        raise ExportNotConfigured(
            "<Service> not configured. Add '<service>' to global.json."
        )
    # Resolve project config overrides
    # Load repositories
    # Build and return service
```

Config precedence: `override arg > project config > global config`.

---

## Step 8: Sync Orchestration

Register in `application/sync/integration_sync.py`:

```python
def run_configured_syncs(..., sync_list: list[str]) -> None:
    for integration in sync_list:
        if integration == "<service>":
            try:
                _sync_<service>(base_path, project_name, run_id)
            except Exception:
                logger.exception(...)
```

Add the private sync function with a lazy import of the factory:

```python
def _sync_<service>(base_path, project_name, run_id):
    from factories.export import create_<service>_export_for_project

    service = create_<service>_export_for_project(
        base_path=base_path,
        project_name=project_name,
        run_id=run_id,
    )
    result = service.export()
    if result.success:
        logger.info("exported %d findings to <Service>", result.findings_exported)
    else:
        for error in result.errors:
            logger.warning("sync: %s", error)
```

If on-demand export is needed, also wire a REPL command and/or API route that
calls the same factory function.

---

## Step 9: Verification

```
1. Connection test
   - Valid credentials: test_connection() returns True
   - Invalid credentials: returns False (no crash)
   - Unreachable host: returns False within timeout

2. Export correctness
   - Findings appear in external service with correct severity/title/fields
   - Tool-specific fields map correctly (spot-check semgrep, gitleaks, SCA)
   - Empty finding set: no error, exported_count = 0

3. Grouping behavior
   - Findings from different repos land in correct targets
   - Findings from different tools don't clobber each other

4. Error handling
   - Auth error (401/403): stops early, reports clearly
   - Server error (500): reports per-group, continues other groups
   - Single mapping failure: skips finding, exports rest

5. Toolchain
   source .venv/bin/activate && make test
   .venv/bin/ruff check .
   .venv/bin/ruff format --check .
   .venv/bin/pyright .
```

---

## Common Mistakes

1. **Severity string mismatch.** External services often expect exact casing
   (`"Critical"` not `"critical"`). Map explicitly, don't pass through raw.

2. **Forgetting empty tool groups.** If a tool ran but produced zero findings,
   some services need an empty import to clear stale data. Handle this case.

3. **Not grouping by repo AND tool.** Sending all findings in one batch causes
   overwrites when the service uses (product, tool) as a unique scope.

4. **Leaking auth tokens.** Never `log.debug("sending to %s with token %s", ...)`
   or include tokens in error messages. Redact in all log output.

5. **SSL verify defaulting to False.** Always default `verify_ssl=True`. Only
   disable when the user explicitly configures it.

6. **Swallowing HTTP error bodies.** The response body on 4xx/5xx contains
   diagnostic info (field validation errors, missing permissions). Parse and
   surface it in `ExportResult.errors`.

7. **Date format mismatches.** `Finding.first_seen` is a datetime; external
   APIs may expect ISO 8601 string, Unix timestamp, or date-only. Convert
   explicitly in the mapper.

8. **Not testing against a real instance.** Unit tests with mocked client are
   necessary but not sufficient. Field mapping bugs only surface when the real
   API validates and rejects payloads.
