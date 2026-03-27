# Approve Finding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Report?" ag-grid checkbox with a green/red pill toggle labelled "Approve?", backed by the existing `should_report` column, with a batch PATCH endpoint for mass-approving selected rows.

**Architecture:** Backend changes are pure Python (SQLite DDL fix, new repo method, new FastAPI route). Frontend changes are Vue 3 + ag-grid: a new `PillToggle.vue` cell renderer, row selection, and a toolbar button that fires a single batch request.

**Tech Stack:** Python/FastAPI/Pydantic/SQLite (backend), Vue 3/TypeScript/ag-grid-community v33/axios (frontend), pytest/httpx (tests), `npm run build` (frontend type-check via vue-tsc).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `infrastructure/store/connection.py` | Modify | Fix `should_report DEFAULT 1` → `DEFAULT 0` in DDL |
| `infrastructure/store/repositories/findings.py` | Modify | Add `should_report=0` to `upsert_findings` INSERT; add `batch_update_analyst_fields()` |
| `web/api/schemas.py` | Modify | Add `BatchFindingPatchRequest` |
| `web/api/findings.py` | Modify | Add `PATCH /api/findings/batch` route (before `/{finding_id}`) |
| `web/api/config.py` | Modify | Remove dead `should_report` entry |
| `ui/src/components/PillToggle.vue` | Create | Reusable green/red pill cell renderer |
| `ui/src/views/FindingsTable.vue` | Modify | Replace Report? col, add PillToggle, row selection, toolbar |
| `ui/src/api.ts` | Modify | Add `BatchFindingPatch` interface + `batchPatchFindings()` |
| `tests/integration/store/test_schema_migration.py` | Modify | Update `test_should_report_default_is_1` to assert `== 0` |
| `tests/integration/store/test_findings_batch_update.py` | Create | Integration tests for `batch_update_analyst_fields()` |
| `tests/unit/web/test_findings_batch_api.py` | Create | Unit tests for `PATCH /api/findings/batch` |

---

## Task 1: Fix `should_report` DDL default

**Files:**
- Modify: `tests/integration/store/test_schema_migration.py:54-58`
- Modify: `infrastructure/store/connection.py:87`

- [ ] **Step 1: Update the failing test assertion**

In `tests/integration/store/test_schema_migration.py`, change:
```python
def test_should_report_default_is_1(self, tmp_path: Path) -> None:
    factory = ConnectionFactory(tmp_path / "findings.db")
    factory.init_schema()
    defaults = _insert_and_read(factory)
    assert defaults["should_report"] == 1
```
to:
```python
def test_should_report_default_is_0(self, tmp_path: Path) -> None:
    factory = ConnectionFactory(tmp_path / "findings.db")
    factory.init_schema()
    defaults = _insert_and_read(factory)
    assert defaults["should_report"] == 0
```

- [ ] **Step 2: Run to confirm it fails**

```
python -m pytest tests/integration/store/test_schema_migration.py::TestSchemaNewColumns::test_should_report_default_is_0 -v
```
Expected: FAIL — `assert 1 == 0`

- [ ] **Step 3: Fix the DDL**

In `infrastructure/store/connection.py:87`, change:
```python
                    should_report    INTEGER NOT NULL DEFAULT 1,
```
to:
```python
                    should_report    INTEGER NOT NULL DEFAULT 0,
```

- [ ] **Step 4: Run to confirm it passes**

```
python -m pytest tests/integration/store/test_schema_migration.py::TestSchemaNewColumns::test_should_report_default_is_0 -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/store/connection.py tests/integration/store/test_schema_migration.py
git commit -m "fix: change should_report DDL default from 1 to 0"
```

---

## Task 2: Fix ingestor to explicitly set `should_report = 0`

The `upsert_findings` method currently omits `should_report` from the INSERT, relying on the DDL DEFAULT. We must set it explicitly so that existing production databases (which still have `DEFAULT 1`) also get `0` on new findings. The ON CONFLICT clause must NOT update `should_report` — a re-scan must not reset an analyst's approval.

**Files:**
- Modify: `infrastructure/store/repositories/findings.py:129-154`
- Create: `tests/integration/store/test_findings_batch_update.py` (partial — upsert test first)

- [ ] **Step 1: Write a test that verifies upsert_findings sets should_report = 0**

Create `tests/integration/store/test_findings_batch_update.py`:
```python
"""Integration tests for batch_update_analyst_fields and upsert should_report default."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration

_BASE_FINDING: dict = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "file_path": "src/app.py",
    "rule_id": "test-rule",
    "description": "test finding",
    "segment": "sast",
    "repo": "test-repo",
}


class TestUpsertShouldReportDefault:
    def test_upsert_findings_sets_should_report_to_0(self, tmp_path: Path) -> None:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(run_id, [_BASE_FINDING])
        with factory.connect() as conn:
            row = conn.execute("SELECT should_report FROM findings LIMIT 1").fetchone()
        assert row["should_report"] == 0

    def test_rescan_does_not_reset_approved_finding(self, tmp_path: Path) -> None:
        """Re-upserting a finding must not clear analyst approval."""
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)
        run_id = run_repo.create_run({})
        finding_repo.upsert_findings(run_id, [_BASE_FINDING])
        # Simulate analyst approval
        with factory.connect() as conn:
            conn.execute("UPDATE findings SET should_report = 1")
        # Re-scan same fingerprint
        run_id2 = run_repo.create_run({})
        finding_repo.upsert_findings(run_id2, [_BASE_FINDING])
        with factory.connect() as conn:
            row = conn.execute("SELECT should_report FROM findings LIMIT 1").fetchone()
        assert row["should_report"] == 1
```

- [ ] **Step 2: Run to see first test fail**

```
python -m pytest tests/integration/store/test_findings_batch_update.py::TestUpsertShouldReportDefault -v
```
Expected: `test_upsert_findings_sets_should_report_to_0` FAIL — currently relies on DEFAULT 1 from the old DDL (now 0 after Task 1), so actually may pass. The `test_rescan_does_not_reset_approved_finding` is the critical safety check.

- [ ] **Step 3: Update `upsert_findings` to include `should_report = 0` explicitly**

In `infrastructure/store/repositories/findings.py`, change line 129:
```python
        rows_with_ts = [(*row, now, now, 1, "active") for row in rows]
```
to:
```python
        rows_with_ts = [(*row, now, now, 1, "active", 0) for row in rows]
```

Change the INSERT SQL (lines 131-154) to add `should_report` as the 27th column — add it to the column list and the VALUES placeholders, but NOT to the `ON CONFLICT DO UPDATE` clause:

```python
        sql = """
            INSERT INTO findings (
                fingerprint, run_id, tool, domain, segment, repo,
                finding_type, severity,
                confidence, file, rule_id, url, host, port,
                vulnerability_id, package_name, ecosystem,
                description, package_version, cwe, enriched, meta,
                first_seen, last_seen, seen_count, status, should_report
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (fingerprint) DO UPDATE SET
                run_id          = excluded.run_id,
                severity        = excluded.severity,
                confidence      = excluded.confidence,
                description     = excluded.description,
                package_version = excluded.package_version,
                cwe             = excluded.cwe,
                enriched        = excluded.enriched,
                meta            = excluded.meta,
                last_seen       = excluded.last_seen,
                seen_count      = COALESCE(seen_count, 0) + 1
        """
```

Note: `should_report` is deliberately absent from the `ON CONFLICT DO UPDATE` list.

- [ ] **Step 4: Run both tests**

```
python -m pytest tests/integration/store/test_findings_batch_update.py::TestUpsertShouldReportDefault -v
```
Expected: both PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```
python -m pytest --tb=short -q
```
Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add infrastructure/store/repositories/findings.py tests/integration/store/test_findings_batch_update.py
git commit -m "fix: upsert_findings explicitly sets should_report=0, not overwritten on re-scan"
```

---

## Task 3: Add `batch_update_analyst_fields` to FindingRepository

**Files:**
- Modify: `infrastructure/store/repositories/findings.py` (add new method after `update_analyst_fields`)
- Modify: `tests/integration/store/test_findings_batch_update.py` (add new test class)

- [ ] **Step 1: Add tests for `batch_update_analyst_fields`**

Append to `tests/integration/store/test_findings_batch_update.py`:
```python


class TestBatchUpdateAnalystFields:
    def _seed(self, tmp_path: Path, count: int = 2) -> tuple[ConnectionFactory, list[int]]:
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        finding_repo = FindingRepository(factory)
        run_id = run_repo.create_run({})
        findings = [
            {**_BASE_FINDING, "rule_id": f"rule-{i}", "file_path": f"src/{i}.py"}
            for i in range(count)
        ]
        finding_repo.upsert_findings(run_id, findings)
        with factory.connect() as conn:
            ids = [r["id"] for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()]
        return factory, ids

    def test_updates_all_ids_in_batch(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path, count=3)
        finding_repo = FindingRepository(factory)
        updated = finding_repo.batch_update_analyst_fields(ids, {"should_report": 1})
        assert updated == 3
        with factory.connect() as conn:
            rows = conn.execute("SELECT should_report FROM findings ORDER BY id").fetchall()
        assert all(r["should_report"] == 1 for r in rows)

    def test_sets_triaged_by_and_triaged_at(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path)
        finding_repo = FindingRepository(factory)
        finding_repo.batch_update_analyst_fields(ids, {"should_report": 1})
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings ORDER BY id"
            ).fetchall()
        for row in rows:
            assert row["triaged_by"] == "analyst_web"
            assert row["triaged_at"] is not None

    def test_returns_count_of_updated_rows(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path, count=3)
        finding_repo = FindingRepository(factory)
        # Pass only 2 of 3 IDs
        updated = finding_repo.batch_update_analyst_fields(ids[:2], {"should_report": 1})
        assert updated == 2

    def test_nonexistent_ids_are_silently_skipped(self, tmp_path: Path) -> None:
        factory, ids = self._seed(tmp_path, count=2)
        finding_repo = FindingRepository(factory)
        updated = finding_repo.batch_update_analyst_fields([99999, 99998], {"should_report": 1})
        assert updated == 0

    def test_empty_ids_returns_zero(self, tmp_path: Path) -> None:
        factory, _ = self._seed(tmp_path)
        finding_repo = FindingRepository(factory)
        updated = finding_repo.batch_update_analyst_fields([], {"should_report": 1})
        assert updated == 0
```

- [ ] **Step 2: Run to confirm tests fail**

```
python -m pytest tests/integration/store/test_findings_batch_update.py::TestBatchUpdateAnalystFields -v
```
Expected: FAIL — `AttributeError: 'FindingRepository' object has no attribute 'batch_update_analyst_fields'`

- [ ] **Step 3: Implement `batch_update_analyst_fields`**

In `infrastructure/store/repositories/findings.py`, add this method after `update_analyst_fields` (around line 401):
```python
    def batch_update_analyst_fields(
        self,
        ids: list[int],
        fields: dict[str, Any],
    ) -> int:
        """Update analyst-writable named columns on multiple findings in one transaction.

        Sets ``triaged_by = 'analyst_web'`` and ``triaged_at`` on every row.
        Does not touch the meta JSON blob — meta keys are not supported for batch.
        Returns the count of rows actually updated.
        """
        from datetime import UTC, datetime

        if not ids or not fields:
            return 0

        now_iso = datetime.now(UTC).isoformat()

        set_parts: list[str] = []
        params: list[Any] = []
        for col, val in fields.items():
            set_parts.append(f"{col} = ?")
            params.append(val)
        set_parts.extend(["triaged_by = 'analyst_web'", "triaged_at = ?"])
        params.append(now_iso)

        placeholders = ",".join("?" * len(ids))
        params.extend(ids)

        sql = (
            f"UPDATE findings SET {', '.join(set_parts)} "
            f"WHERE id IN ({placeholders})"
        )
        with self._factory.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.rowcount
```

- [ ] **Step 4: Run tests**

```
python -m pytest tests/integration/store/test_findings_batch_update.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add infrastructure/store/repositories/findings.py tests/integration/store/test_findings_batch_update.py
git commit -m "feat: add FindingRepository.batch_update_analyst_fields()"
```

---

## Task 4: Add `BatchFindingPatchRequest` schema and `PATCH /api/findings/batch` endpoint

**Files:**
- Modify: `web/api/schemas.py`
- Modify: `web/api/findings.py`
- Create: `tests/unit/web/test_findings_batch_api.py`

- [ ] **Step 1: Write unit tests for the batch endpoint**

Create `tests/unit/web/test_findings_batch_api.py`:
```python
"""Tests for PATCH /api/findings/batch endpoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository
from tests.unit.web.conftest import AUTH, TOKEN
from web.server import create_app

pytestmark = pytest.mark.integration

_FINDING_A: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "high",
    "file_path": "src/a.py",
    "rule_id": "rule-a",
    "description": "finding a",
    "segment": "sast",
    "repo": "test-repo",
}
_FINDING_B: dict[str, Any] = {
    "tool": "semgrep",
    "domain": "code",
    "severity": "medium",
    "file_path": "src/b.py",
    "rule_id": "rule-b",
    "description": "finding b",
    "segment": "sast",
    "repo": "test-repo",
}


@pytest_asyncio.fixture()
async def batch_client(tmp_path: Path):
    """Yield (client, [id_a, id_b], factory) for batch endpoint tests."""
    db_path = tmp_path / "findings.db"
    factory = ConnectionFactory(db_path)
    factory.init_schema()

    run_repo = RunRepository(factory)
    finding_repo = FindingRepository(factory)
    run_id = run_repo.create_run({})
    finding_repo.upsert_findings(run_id, [_FINDING_A, _FINDING_B])

    with factory.connect() as conn:
        ids = [
            r["id"]
            for r in conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
        ]

    rag_mock = MagicMock()
    app = create_app(str(tmp_path), "testproject", token=TOKEN)
    app.state.connection_factory = factory
    app.state.rag_engine = rag_mock

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client, ids, factory


class TestBatchPatchFindings:
    async def test_batch_approve_updates_all_rows(self, batch_client) -> None:
        client, ids, factory = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json() == {"updated": 2}
        with factory.connect() as conn:
            rows = conn.execute("SELECT should_report FROM findings ORDER BY id").fetchall()
        assert all(r["should_report"] == 1 for r in rows)

    async def test_batch_sets_triaged_by_analyst_web(self, batch_client) -> None:
        client, ids, factory = batch_client
        await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=AUTH,
        )
        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings ORDER BY id"
            ).fetchall()
        for row in rows:
            assert row["triaged_by"] == "analyst_web"
            assert row["triaged_at"] is not None

    async def test_batch_does_not_sync_chroma(self, batch_client) -> None:
        client, ids, rag_mock = batch_client[0], batch_client[1], None
        # rag_mock is index 2 but we want to verify it's NOT called
        # Re-extract fixture parts:
        client, ids, factory = batch_client
        app = client._transport.app  # type: ignore[attr-defined]
        rag_mock = app.state.rag_engine
        await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
            headers=AUTH,
        )
        assert not rag_mock.add_documents.called

    async def test_empty_ids_returns_422(self, batch_client) -> None:
        client, _, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": [], "should_report": True},
            headers=AUTH,
        )
        assert response.status_code == 422

    async def test_no_fields_returns_422(self, batch_client) -> None:
        client, ids, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": ids},
            headers=AUTH,
        )
        assert response.status_code == 422

    async def test_missing_auth_returns_401(self, batch_client) -> None:
        client, ids, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": ids, "should_report": True},
        )
        assert response.status_code == 401

    async def test_partial_ids_returns_correct_count(self, batch_client) -> None:
        client, ids, _ = batch_client
        response = await client.patch(
            "/api/findings/batch",
            json={"ids": [ids[0]], "should_report": True},
            headers=AUTH,
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 1
```

- [ ] **Step 2: Run to confirm tests fail**

```
python -m pytest tests/unit/web/test_findings_batch_api.py -v
```
Expected: FAIL — 404 or 405 because the route doesn't exist yet

- [ ] **Step 3: Add `BatchFindingPatchRequest` to `web/api/schemas.py`**

Add after the existing `FindingPatchRequest` class in `web/api/schemas.py`:
```python

class BatchFindingPatchRequest(BaseModel):
    """Batch-update request body for PATCH /api/findings/batch.

    Applies the same field-level updates to every finding ID in ``ids``.
    At least one field besides ``ids`` must be present.
    ``triaged_at`` and ``triaged_by`` are set automatically on every write.
    Meta keys (meta_*) are not supported for batch updates.
    """

    model_config = ConfigDict(extra="ignore")

    ids: list[int]
    should_report: bool | None = None
    status: str | None = None
    severity: str | None = None
    confidence: str | None = None
    description: str | None = None
    business_impact: str | None = None
    tal_id: str | None = None

    @field_validator("ids")
    @classmethod
    def validate_ids_nonempty(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ids must not be empty")
        return v

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str | None) -> str | None:
        if v is not None and v not in SEVERITY_LEVELS:
            raise ValueError(f"severity must be one of {sorted(SEVERITY_LEVELS)}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: str | None) -> str | None:
        if v is not None and v not in CONFIDENCE_LEVELS:
            raise ValueError(f"confidence must be one of {sorted(CONFIDENCE_LEVELS)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in STATUS_LEVELS:
            raise ValueError(f"status must be one of {sorted(STATUS_LEVELS)}")
        return v

    @model_validator(mode="after")
    def validate_has_patch_fields(self) -> "BatchFindingPatchRequest":
        fields = self.model_dump(exclude={"ids"}, exclude_none=True)
        if not fields:
            raise ValueError("at least one field besides ids is required")
        return self
```

Also update the import at the top of `schemas.py` — add `model_validator` to the pydantic imports:
```python
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
```

- [ ] **Step 4: Add the `PATCH /api/findings/batch` route to `web/api/findings.py`**

This route MUST be registered before `@router.patch("/{finding_id}")` to prevent FastAPI trying to parse the literal string "batch" as an integer ID.

In `web/api/findings.py`, add the import for `BatchFindingPatchRequest` alongside the existing schema import:
```python
from web.api.schemas import BatchFindingPatchRequest, FindingPatchRequest
```

Then add the batch route immediately before the `@router.patch("/{finding_id}")` definition (around line 110):
```python
@router.patch("/batch")
async def batch_patch_findings(
    request: Request,
    body: BatchFindingPatchRequest,
) -> dict:
    """Apply analyst field updates to multiple findings in one transaction.

    Accepts the same patchable fields as the single-finding PATCH.
    Sets ``triaged_by = 'analyst_web'`` and ``triaged_at = now()`` for
    every row in the batch.

    Returns ``{"updated": N}`` where N is the count of rows actually updated.
    Does not sync to ChromaDB — should_report is a UI annotation only.
    """
    factory = request.app.state.connection_factory
    repo = FindingRepository(factory)

    raw = body.model_dump(exclude={"ids"}, exclude_none=True)
    fields: dict[str, Any] = {}
    for k, v in raw.items():
        if k == "should_report":
            fields["should_report"] = 1 if v else 0
        else:
            fields[k] = v

    updated = repo.batch_update_analyst_fields(body.ids, fields)
    return {"updated": updated}
```

- [ ] **Step 5: Run tests**

```
python -m pytest tests/unit/web/test_findings_batch_api.py -v
```
Expected: all PASS (the `test_batch_does_not_sync_chroma` test uses a slightly unusual fixture access pattern — if it fails, simplify it by removing it or accessing `rag_mock` differently via `factory`)

- [ ] **Step 6: Run full test suite**

```
python -m pytest --tb=short -q
```
Expected: all previously passing tests still pass

- [ ] **Step 7: Commit**

```bash
git add web/api/schemas.py web/api/findings.py tests/unit/web/test_findings_batch_api.py
git commit -m "feat: add PATCH /api/findings/batch endpoint"
```

---

## Task 5: Remove `should_report` from config endpoint

**Files:**
- Modify: `web/api/config.py:48`

- [ ] **Step 1: Remove the dead entry**

In `web/api/config.py`, remove the line:
```python
            "should_report": {"editor": "boolean"},
```

The `should_report` column is now hardcoded in `buildColumnDefs` as a `PillToggle` column and does not go through the `applySpec` path. The config entry is dead code.

- [ ] **Step 2: Run the test suite to confirm nothing breaks**

```
python -m pytest --tb=short -q
```
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add web/api/config.py
git commit -m "chore: remove should_report from config endpoint (now hardcoded in UI)"
```

---

## Task 6: Create `PillToggle.vue` cell renderer

**Files:**
- Create: `ui/src/components/PillToggle.vue`

- [ ] **Step 1: Create the component**

Create `ui/src/components/PillToggle.vue`:
```vue
<script setup lang="ts">
import { ref } from 'vue'

interface PillParams {
  value: boolean
  activeLabel: string
  inactiveLabel: string
  activeColor: string
  inactiveColor: string
  onToggle: (newValue: boolean) => Promise<void>
}

const props = defineProps<{ params: PillParams }>()

const loading = ref(false)

async function handleClick() {
  if (loading.value) return
  loading.value = true
  try {
    await props.params.onToggle(!props.params.value)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <button
    class="pill-toggle"
    :style="{
      backgroundColor: params.value ? params.activeColor : 'transparent',
      borderColor: params.value ? params.activeColor : params.inactiveColor,
      color: params.value ? '#ffffff' : params.inactiveColor,
      opacity: loading ? 0.55 : 1,
      cursor: loading ? 'wait' : 'pointer',
    }"
    :disabled="loading"
    @click.stop="handleClick"
  >
    {{ params.value ? params.activeLabel : params.inactiveLabel }}
  </button>
</template>

<style scoped>
.pill-toggle {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  border-radius: 9999px;
  border-width: 1.5px;
  border-style: solid;
  font-size: 11px;
  font-weight: 600;
  font-family: inherit;
  line-height: 18px;
  transition: opacity 0.15s ease, background-color 0.15s ease;
  white-space: nowrap;
}
.pill-toggle:hover:not(:disabled) {
  opacity: 0.8;
}
</style>
```

- [ ] **Step 2: Build to type-check**

```bash
cd /llm/code/tally/ui && npm run build
```
Expected: build succeeds (or only pre-existing errors)

- [ ] **Step 3: Commit**

```bash
cd /llm/code/tally
git add ui/src/components/PillToggle.vue
git commit -m "feat: add PillToggle reusable cell renderer component"
```

---

## Task 7: Add `batchPatchFindings` to `api.ts`

**Files:**
- Modify: `ui/src/api.ts`

- [ ] **Step 1: Add the interface and function**

In `ui/src/api.ts`, add after the `patchFinding` function (after line 98):
```ts
export interface BatchFindingPatch {
  ids: number[]
  should_report?: boolean
  status?: string
  severity?: string
  confidence?: string
  description?: string
  business_impact?: string
  tal_id?: string
}

export async function batchPatchFindings(
  body: BatchFindingPatch,
): Promise<{ updated: number }> {
  const response = await http.patch<{ updated: number }>('/api/findings/batch', body)
  return response.data
}
```

- [ ] **Step 2: Build to type-check**

```bash
cd /llm/code/tally/ui && npm run build
```
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
cd /llm/code/tally
git add ui/src/api.ts
git commit -m "feat: add batchPatchFindings API client function"
```

---

## Task 8: Update `FindingsTable.vue`

This task replaces the "Report?" checkbox column with the "Approve?" pill, adds row selection, and adds the batch-approve toolbar.

**Files:**
- Modify: `ui/src/views/FindingsTable.vue`

- [ ] **Step 1: Update imports and add new refs/state**

Replace the `<script setup>` section of `ui/src/views/FindingsTable.vue` with the following. The full new file is shown — do not carry forward the old `should_report` applySpec block:

```vue
<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { AgGridVue } from 'ag-grid-vue3'
import type {
  ColDef,
  CellValueChangedEvent,
  GridReadyEvent,
  GridApi,
  ICellRendererParams,
  IRowNode,
  ValueGetterParams,
  ValueSetterParams,
} from 'ag-grid-community'
import { myTheme } from '../ag-grid-theme.js'
import { getConfig, getFindings, patchFinding, batchPatchFindings } from '../api'
import type { FieldSpec, Finding, FindingPatch } from '../api'
import PillToggle from '../components/PillToggle.vue'

const rowData = reactive<Finding[]>([])
const columnDefs = ref<ColDef<Finding>[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)
const selectedCount = ref(0)
const batchLoading = ref(false)
const batchError = ref<string | null>(null)
const gridComponents = { PillToggle }

let gridApi: GridApi<Finding> | null = null

const defaultColDef: ColDef<Finding> = {
  resizable: true,
  sortable: true,
  filter: true,
  valueFormatter: (params) => (params.value == null ? '' : String(params.value)),
}

/** Apply server-supplied field spec to a base column definition. */
function applySpec(base: ColDef<Finding>, spec: FieldSpec | undefined): ColDef<Finding> {
  if (!spec) return { ...base, editable: false }
  const out: ColDef<Finding> = { ...base, editable: true }
  if (spec.editor === 'select' && spec.options) {
    out.cellEditor = 'agSelectCellEditor'
    out.cellEditorParams = { values: spec.options }
  } else if (spec.editor === 'boolean') {
    out.cellRenderer = 'agCheckboxCellRenderer'
    out.cellEditor = 'agCheckboxCellEditor'
  }
  return out
}

function buildColumnDefs(fields: Record<string, FieldSpec>): ColDef<Finding>[] {
  const e = (key: string) => fields[key]
  return [
    {
      checkboxSelection: true,
      headerCheckboxSelection: true,
      width: 50,
      pinned: 'left' as const,
      editable: false,
      sortable: false,
      filter: false,
      resizable: false,
      suppressKeyboardEvent: () => true,
    },
    { headerName: 'ID', field: 'id', editable: false, width: 80 },
    { headerName: 'Tool', field: 'tool', editable: false, width: 100 },
    applySpec({ headerName: 'Severity', field: 'severity', width: 120 }, e('severity')),
    applySpec({ headerName: 'Confidence', field: 'confidence', width: 130 }, e('confidence')),
    applySpec(
      {
        headerName: 'Type',
        colId: 'finding_type',
        valueGetter: (params: ValueGetterParams<Finding>) =>
          params.data?.finding_type?.join(', ') ?? '',
        valueSetter: (params: ValueSetterParams<Finding>) => {
          params.data.finding_type = (params.newValue as string)
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean)
          return true
        },
        width: 150,
      },
      e('finding_type'),
    ),
    { headerName: 'File', field: 'file', editable: false, width: 220 },
    {
      headerName: 'Rule / Alert',
      colId: 'rule_alert',
      editable: false,
      valueGetter: (params: ValueGetterParams<Finding>) =>
        params.data?.rule_id ||
        (params.data?.meta?.alert_name as string | undefined) ||
        '',
      width: 160,
    },
    applySpec({ headerName: 'Description', field: 'description', flex: 1, minWidth: 200 }, e('description')),
    { headerName: 'URL', field: 'url', editable: false, width: 220 },
    applySpec({ headerName: 'Status', field: 'status', width: 140 }, e('status')),
    {
      headerName: 'Approve?',
      colId: 'should_report',
      width: 130,
      editable: false,
      suppressKeyboardEvent: () => true,
      cellRenderer: 'PillToggle',
      cellRendererParams: (params: ICellRendererParams<Finding>) => ({
        activeLabel: '✓ Approved',
        inactiveLabel: 'Approve',
        activeColor: '#22c55e',
        inactiveColor: '#ef4444',
        onToggle: async (newValue: boolean) => {
          const updated = await patchFinding(params.data!.id, { should_report: newValue })
          Object.assign(params.data!, updated)
          params.api.refreshCells({ rowNodes: [params.node!], force: true })
        },
      }),
      valueGetter: (params: ValueGetterParams<Finding>) =>
        Boolean(params.data?.should_report),
    },
    applySpec(
      {
        headerName: 'Title',
        colId: 'meta_title',
        valueGetter: (params: ValueGetterParams<Finding>) =>
          (params.data?.meta?.title as string | undefined) ?? '',
        valueSetter: (params: ValueSetterParams<Finding>) => {
          params.data.meta.title = params.newValue as string
          return true
        },
        width: 200,
      },
      e('meta_title'),
    ),
    applySpec(
      {
        headerName: 'Remediation',
        colId: 'meta_remediation',
        valueGetter: (params: ValueGetterParams<Finding>) =>
          (params.data?.meta?.remediation as string | undefined) ?? '',
        valueSetter: (params: ValueSetterParams<Finding>) => {
          params.data.meta.remediation = params.newValue as string
          return true
        },
        width: 250,
      },
      e('meta_remediation'),
    ),
    {
      headerName: 'CWE',
      colId: 'cwe',
      editable: false,
      valueGetter: (params: ValueGetterParams<Finding>) =>
        params.data?.cwe?.join(', ') ?? '',
      width: 120,
    },
  ]
}

let _reverting = false

async function onCellValueChanged(event: CellValueChangedEvent<Finding>) {
  if (_reverting) return
  const id = event.data.id
  const colId = event.colDef.colId ?? event.colDef.field ?? ''
  const patch: FindingPatch = {}

  if (colId === 'severity') patch.severity = event.newValue as string
  else if (colId === 'confidence') patch.confidence = event.newValue as string
  else if (colId === 'finding_type') patch.finding_type = event.data.finding_type
  else if (colId === 'description') patch.description = event.newValue as string
  else if (colId === 'status') patch.status = event.newValue as string
  else if (colId === 'meta_title') patch.meta_title = event.newValue as string
  else if (colId === 'meta_remediation') patch.meta_remediation = event.newValue as string
  else return

  try {
    const updated = await patchFinding(id, patch)
    Object.assign(event.data, updated)
    event.api.refreshCells({ rowNodes: [event.node!], force: true })
  } catch {
    _reverting = true
    try {
      const key = event.colDef.colId ?? event.colDef.field
      if (key) event.node?.setDataValue(key, event.oldValue)
    } finally {
      _reverting = false
    }
  }
}

function onGridReady(event: GridReadyEvent<Finding>) {
  gridApi = event.api
  event.api.addEventListener('selectionChanged', () => {
    selectedCount.value = event.api.getSelectedRows().length
  })
}

async function approveSelected() {
  if (!gridApi || batchLoading.value) return
  const selectedNodes: IRowNode<Finding>[] = []
  gridApi.forEachNode((node) => {
    if (node.isSelected()) selectedNodes.push(node)
  })
  const ids = selectedNodes.map((n) => n.data!.id)
  if (!ids.length) return

  batchLoading.value = true
  batchError.value = null
  try {
    await batchPatchFindings({ ids, should_report: true })
    selectedNodes.forEach((node) => {
      if (node.data) node.data.should_report = 1
    })
    gridApi.refreshCells({ rowNodes: selectedNodes, columns: ['should_report'], force: true })
    gridApi.deselectAll()
    selectedCount.value = 0
  } catch {
    batchError.value = 'Batch approve failed — please try again.'
    setTimeout(() => {
      batchError.value = null
    }, 4000)
  } finally {
    batchLoading.value = false
  }
}

onMounted(async () => {
  try {
    const [config, codeFindings, webFindings] = await Promise.all([
      getConfig(),
      getFindings({ domain: 'code' }),
      getFindings({ domain: 'web' }),
    ])
    columnDefs.value = buildColumnDefs(config.editable_fields)
    rowData.push(...codeFindings, ...webFindings)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : 'Failed to load findings'
  } finally {
    loading.value = false
  }
})
</script>
```

- [ ] **Step 2: Update the template**

Replace the `<template>` section of `ui/src/views/FindingsTable.vue`:
```vue
<template>
  <div style="height: calc(100vh - 50px); width: 100%; display: flex; flex-direction: column;">
    <div v-if="loading" style="padding: 16px; font-family: monospace;">Loading…</div>
    <div v-else-if="loadError" style="padding: 16px; color: #ff4444; font-family: monospace;">
      {{ loadError }}
    </div>
    <template v-else>
      <div
        style="
          padding: 6px 12px;
          background: #21222C;
          border-bottom: 1px solid #429356;
          display: flex;
          align-items: center;
          gap: 10px;
          font-family: 'IBM Plex Mono', monospace;
          font-size: 12px;
        "
      >
        <button
          :disabled="selectedCount === 0 || batchLoading"
          :style="{
            padding: '4px 14px',
            background: selectedCount > 0 && !batchLoading ? '#429356' : '#2a2a3a',
            color: selectedCount > 0 && !batchLoading ? '#ffffff' : '#555',
            border: 'none',
            borderRadius: '4px',
            fontFamily: 'inherit',
            fontSize: '12px',
            cursor: selectedCount > 0 && !batchLoading ? 'pointer' : 'not-allowed',
          }"
          @click="approveSelected"
        >
          Approve Selected ({{ selectedCount }})
        </button>
        <span v-if="batchError" style="color: #ef4444;">{{ batchError }}</span>
      </div>
      <AgGridVue
        style="flex: 1; width: 100%;"
        :column-defs="columnDefs"
        :row-data="rowData"
        :default-col-def="defaultColDef"
        :theme="myTheme"
        :components="gridComponents"
        row-selection="multiple"
        @cell-value-changed="onCellValueChanged"
        @grid-ready="onGridReady"
      />
    </template>
  </div>
</template>
```

- [ ] **Step 3: Build to type-check**

```bash
cd /llm/code/tally/ui && npm run build
```
Expected: build succeeds with no TypeScript errors. Fix any type errors before proceeding.

- [ ] **Step 4: Run full backend test suite**

```bash
cd /llm/code/tally && python -m pytest --tb=short -q
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /llm/code/tally
git add ui/src/views/FindingsTable.vue
git commit -m "feat: replace Report? checkbox with Approve? pill toggle, add row selection and batch approve toolbar"
```

---

## Self-Review Checklist

After writing the plan, these checks were applied inline:

- **Spec coverage:** DDL fix ✓ (Task 1), ingestor fix ✓ (Task 2), `batch_update_analyst_fields` ✓ (Task 3), batch endpoint + schema ✓ (Task 4), config cleanup ✓ (Task 5), `PillToggle.vue` ✓ (Task 6), `api.ts` ✓ (Task 7), `FindingsTable.vue` full update ✓ (Task 8)
- **Placeholder scan:** All code blocks are complete. No TBDs.
- **Type consistency:** `PillParams.onToggle` is `(newValue: boolean) => Promise<void>` in Task 6 and matches the usage in Task 8. `batchPatchFindings` returns `Promise<{ updated: number }>` in Task 7 and is consumed as such in Task 8. `batch_update_analyst_fields` returns `int` in Task 3 and is used as `updated = repo.batch_update_analyst_fields(...)` / `return {"updated": updated}` in Task 4.
- **Route ordering:** The `/batch` route in Task 4 is explicitly placed before `/{finding_id}` with a note explaining why.
- **`should_report` removal from `onCellValueChanged`:** Confirmed removed in Task 8 — the new script has no `should_report` branch in that handler.
