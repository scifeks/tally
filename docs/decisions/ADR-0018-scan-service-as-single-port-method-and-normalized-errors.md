# ADR-0018 - ScanService as the single core port for scans, with normalized error egress

**Status:** Accepted
**Date:** 2026-04-29

---

## Context

The two-tier `LockRegistry` in `application/locking/registry.py` was
designed to live in the **core** application layer, not in either
adapter. Tier-1 protects against concurrent same-kind jobs (one of
`scan` / `triage` / `report` at a time); Tier-2 prevents two writers
from clobbering the same finding. The intent has always been that
adapters call into a core use case and let the core acquire its own
locks - the lock registry is an implementation detail of the core, not
a public surface that adapters can call.

Over time the web adapter drifted from that intent. `web/api/scans.py`
acquired the Tier-1 `scan` slot directly with
`get_registry().acquire_job("scan", "scan-web:<uuid>")` so it could fail
fast with HTTP 409 in the request thread before returning 202. The
background worker in `web/scans/runner.py` then constructed a
`ScanOrchestrator`, which itself called `_scan_lock` →
`LockRegistry.job("scan", "scan-run:<run_id>")`. Two acquisitions
against the same `kind="scan"` slot, with different holder tokens -
the second always raised `JobBusy`, so **every web-initiated scan
failed on the first try**:

```
application.locking.exceptions.JobBusy:
  job slot 'scan' is already held by 'scan-web:29b8d799'
```

The failure was silent end-to-end:

- 202 had already been returned, so the API caller got no signal.
- The worker thread caught `Exception`, logged to file, and exited.
- No `RunFailed` SSE event was emitted.
- The `scan_runs` row stayed at `running` forever.

Two distinct things had broken: (a) Tier-1 lock placement leaked out of
the core and into the adapter, where it duplicated the orchestrator's
acquisition; and (b) the worker thread had no normalized error egress -
neither port could learn that a scan had failed during setup.

## Decision

**1. Adapters call exactly one core method to start a scan.**

A new core service `application.tools.scan_service.ScanService` exposes
`start_scan(...)` as the single port that both the REPL and Web
adapters consume. The service owns the entire start-scan lifecycle:

- Tier-1 `scan` slot acquisition (raises `JobBusy` if already held).
- `scan_runs` row creation via `RunRepository.create`.
- Cancel-token registration in `ScanRunRegistry`.
- Daemon worker thread spawning and orchestrator wiring.
- Tier-1 lock release and registry unregistration in `finally`.

`ScanRunRegistry` has been moved from `web/adapters/scan_run_registry.py`
to `application/tools/scan_run_registry.py` because it tracks core run
state, not adapter state. `ScanOrchestrator._scan_lock` and the
`lock_registry` constructor argument are removed - the orchestrator no
longer touches `LockRegistry`. `web/scans/runner.py` is deleted; its
logic now lives in `ScanService._run_worker`. The REPL helpers
`_create_sqlite_run` and `_make_orchestrator` are removed; the REPL
calls `get_scan_service().start_scan(...)` and is otherwise concerned
only with input parsing, the DAST-without-discovery prompt, and
post-scan `add_run_tools` bookkeeping.

**2. A single normalized error contract, surfaced through three
lockstep channels.**

`start_scan(...)` returns a `ScanHandle(run_id, result: Future[ScanSummary])`.
Errors are surfaced as follows:

| Source                                | Channel                                                                                                                  |
|---------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Synchronous (JobBusy, validation)     | Raised out of `start_scan(...)` directly. Adapters catch and translate to HTTP 409 / REPL console message.               |
| Asynchronous, body-stage              | Orchestrator persists `scan_runs.status='failed'` + emits `RunFailed`; the worker re-raises into `Future.set_exception`. |
| Asynchronous, setup-stage             | Worker persists `scan_runs.status='failed'` + emits `RunFailed` itself, then `Future.set_exception`.                     |

The three channels - `Future` exception, `RunFailed` SSE event, and
persisted row status - fire in lockstep so neither adapter is left
blind. The REPL blocks on `handle.result.result()` and prints whichever
exception comes back; the Web adapter ignores the future and observes
the SSE stream and the history GET.

## Consequences

- **The original bug is fixed.** There is exactly one Tier-1 lock
  acquisition per scan, performed in `ScanService.start_scan` before
  the worker thread is spawned. `JobBusy` raised here surfaces
  synchronously to the caller (HTTP 409, REPL console message), exactly
  matching the previous fast-fail intent without the duplicate
  acquisition.
- **No more silent failures.** Setup-time exceptions
  (`discover_tools`, `PipelineFactory.create`, orchestrator
  construction) that previously vanished into the runner's swallowed
  `except Exception` now persist `status='failed'`, emit `RunFailed`,
  and resolve the Future's exception. The UI's existing `run_failed`
  handler flips status to red and appends a log row; the history GET
  returns `failed`.
- **Adapters stop importing `LockRegistry`.** `web/api/scans.py` no
  longer calls `acquire_job` / `release_job` directly. The adapter is
  now a true thin shim over the core port.
- **The orchestrator becomes simpler.** `_scan_lock` and the
  `lock_registry` constructor parameter are gone. Tests that
  constructed `ScanOrchestrator(lock_registry=...)` need updating -
  see follow-up in test sweep.
- **`web/scans/runner.py` is deleted.** All scan-startup orchestration
  is in the core. Triage and reports still use their own
  adapter-level runner files; bringing them into a similar service is
  a separate ADR if pursued.
- **REPL behaviour is functionally identical** for the user: type
  `scan`, see live output, scan finishes, prompt returns. Internally
  the scan now runs on a daemon worker thread and the REPL main
  thread blocks on `handle.result.result()`. `Ctrl+C` while a scan is
  running interrupts the wait but does not signal the cancel token -
  the daemon thread continues until process exit. Wiring `Ctrl+C` to
  `cancel_token.set()` is left as a separate small enhancement.

## Alternatives considered

**Keep the inner-lock + pass an `external_scan_lock=True` flag.** The
minimum patch: add a flag to `ScanOrchestrator` so the web adapter's
existing outer acquisition works without colliding with the
orchestrator's inner one. Rejected - it leaves
`LockRegistry.acquire_job` calls in the adapter, preserving exactly the
architectural smell that caused this bug. The flag would say "the
adapter knows what it's doing with the lock," which is the inverted
relationship.

**Split the orchestrator into `claim_scan` + `execute_claimed_scan`
and expose both to adapters.** The adapter calls `claim_scan`
synchronously (returns 409 or 202) and dispatches `execute_claimed_scan`
to a thread itself. Rejected - it forces every adapter to know there
are two phases, duplicates the threading-vs-sync choice across
adapters, and makes the REPL reach into core lifecycle details. The
single `start_scan` method hides the two-phase implementation.

**Keep `ScanRunRegistry` in `web/adapters/`.** Considered briefly
because the cancel endpoints already imported it from there. Rejected -
the registry tracks core run state with no web concerns, and leaving it
in the adapter layer would force the new core service to import from
`web/`, a layering inversion. Moved to `application/tools/`.

## Related decisions

- ADR-0017: async streaming LLM adapter (closest prior touch on
  hexagonal layering for adapters; informs the "thin shim over the
  core" principle this ADR extends to scans).
