# Credential and Billing Model

Tally runs AI-assisted triage and vulnerability scans through Anthropic's Claude. There are two orthogonal choices for every run: the interaction mode (who drives the session) and, for background runs, the billing method (which Anthropic credential pays for the work).

This page describes both, the four supported credential configurations, and the auto-failover and resume behavior around rate limits.

---

## Interaction mode

Interaction mode is picked per run. The two modes are independent of the billing method.

- `interactive`: you drive Claude Code yourself from your own terminal, and Tally exposes an MCP server that your session calls into. Your local `claude` binary handles authentication; Tally plays no part in that flow.
- `background`: Tally spawns a managed Agent SDK process that runs the orchestration skill unattended. The user does not sit at the terminal while the run executes.

Both modes work with either billing method. Interactive mode is always available because a user can always start Claude Code on their own machine.

---

## Billing method

Billing method applies only to background runs. It picks which Anthropic credential the subprocess sees.

- `plan`: Tally spawns the subprocess with `ANTHROPIC_API_KEY` removed from the child environment. The Agent SDK falls back to the ambient OAuth session that `claude /login` or `claude setup-token` set up. Usage counts against your Claude plan's rate limits, same pool as interactive Claude Code.
- `api`: Tally spawns the subprocess with `ANTHROPIC_API_KEY` present in the child environment, sourced from `claude.api_key` or the ambient env var. Usage counts against API credits attached to that key (monthly plan allocation first, then pay-as-you-go API rates).

The Agent SDK and the `claude` binary prefer `ANTHROPIC_API_KEY` over any OAuth session when both are present. Tally has to actively control the subprocess environment so a user who wants plan billing but also has an API key configured does not silently end up on the API path.

---

## The four supported configurations

Tally never chooses between these; the Agent SDK or `claude` binary picks the ambient credential by its own precedence. Tally only records which path was active when each unit of work ran.

| Config | Auth source | What it bills against | When to use |
|---|---|---|---|
| 1 | `claude /login` or `claude setup-token` (OAuth session) | Plan rate limits, same pool as interactive Claude Code | Plan subscribers who want the cheapest option and are OK sharing quota with foreground work |
| 2 | `ANTHROPIC_API_KEY` from a Console org linked to the plan | Monthly API credit allocation ($100 Max, $200 Ultra), then per-token API rates | Plan subscribers who hit plan rate limits mid-run and want to keep going on API credits |
| 3 | `ANTHROPIC_API_KEY` from a Console org linked to the plan | Same credit allocation | Plan subscribers who deliberately want Tally runs billed separately from interactive quota (chargeback, isolation) |
| 4 | `ANTHROPIC_API_KEY` not linked to a plan | Pure pay-as-you-go API rates | Users without a Claude plan |

For the compliance basis behind config 1, see Anthropic's help center article "Use the Claude Agent SDK with your Claude plan," which confirms that when signed in with a Claude plan, the Agent SDK and `claude -p` draw from subscription limits. Tally sits on the end-user side of this (user runs the tool on their own machine with their own credentials), not the developer-building-a-product side that must use API key auth. Tally does not intermediate credentials. See also Anthropic's "Legal and Compliance" page for Claude Code.

---

## Setup

### Plan OAuth (desktop)

Run `claude /login` once. It opens a browser, you sign in, and the `claude` binary stores the OAuth session where it manages its own credentials. Tally never reads that storage.

Tally detects plan availability by running `claude auth status` as a subprocess probe. If the probe exits 0, plan billing is available. Timeout: 5 seconds. The probe is read-only; no state is persisted on the Tally side.

### Plan OAuth (CI or headless)

Run `claude setup-token` interactively once to produce a long-lived token, then set it as an environment variable in your CI job:

```
CLAUDE_CODE_OAUTH_TOKEN=<token>
```

Tally honors this env var as a short-circuit for the OAuth probe: when it is set and non-empty, plan billing is reported as available without invoking `claude auth status`. This is the headless CI path.

### API key

Set `ANTHROPIC_API_KEY` in your environment, or set `claude.api_key` in `config/global.json`:

```json
{
  "claude": {
    "api_key": "sk-...",
    "model": "claude-opus-4-6[1m]"
  }
}
```

Either source makes API billing available. The env var takes precedence over the config value when both are set.

### Default billing method

Set `claude.default_billing_method` in `config/global.json`:

```json
{
  "claude": {
    "default_billing_method": "plan"
  }
}
```

Accepted values: `"plan"`, `"api"`, or null/empty/absent (unset). The value is case-insensitive.

Env-var fallback: `ANTHROPIC_DEFAULT_BILLING_METHOD` is read when the config field is unset. The config value always wins when set.

An explicit `--billing-method` on a CLI or API request always wins over the configured default.

---

## Default billing method and auto-failover

The resolved billing method for a background run depends on `claude.default_billing_method`:

- `plan`: Tally always starts background runs on plan billing. On rate limit, Tally aborts with the standard rate-limit flow; the user resumes manually.
- `api`: Tally always starts background runs on API billing. Same abort-on-rate-limit behavior.
- unset (null/empty/absent): Tally starts on plan and, on `RATE_LIMIT_PLAN`, automatically starts a resume execution on API billing without user intervention. If the API attempt then also hits `RATE_LIMIT_API`, the run aborts with no further automatic failover.

Automatic failover only runs in the plan-then-API direction, never the reverse: once a user is on API credits, Tally does not assume plan quota has recovered.

Auto-failover applies to **triage only**. Scans do not auto-fail-over. A rate-limited scan sets `scan_runs.status = "rate_limited"` and waits for the user to resume manually on a different billing method.

If the configured default's required credential is not available (for example `default_billing_method=plan` but no OAuth session detected), Tally reports the mismatch at run start and offers the available billing methods for an explicit pick rather than silently falling back.

---

## Rate-limit flow

When a background run hits an Anthropic rate limit, Tally classifies the error and acts based on the usage pool and the auto-failover rules.

### Triage

Per-batch attempts are recorded in `triage_batch_executions`:

- First attempt on plan hits `RATE_LIMIT_PLAN`. Tally writes a row with `usage_pool="plan"`, `status="rate_limited"`, emits `BatchAttemptRateLimited`, and either triggers auto-failover (if permitted and an API key is available) or stops.
- Auto-failover attempt on API: Tally writes a second row with `usage_pool="api"`. If the attempt succeeds, status is `completed`. If it also rate-limits, status is `rate_limited` and the run aborts.
- Manual resume: a user issues the resume request with the billing method they want. Tally writes a new attempt row with that `usage_pool`.

SSE events the user can observe during a background triage run: `BatchAttemptStarted`, `BatchAttemptRateLimited`, `BatchAttemptCompleted`, `BatchAttemptFailed`, `RunRateLimited`.

### Scans

Per-phase attempts are recorded in `scan_phase_executions`:

- First attempt on plan hits `RATE_LIMIT_PLAN` during a phase. The skill marks the phase `rate_limited` and the SDK session exits. Tally writes `scan_runs.status = "rate_limited"` and emits `RunRateLimited`.
- Resume: the user issues a resume request with a different `billing_method`. The resume route reads `scan_phase_executions` and tells the skill which phases are already completed, so work only re-starts on incomplete phases. The phase that rate-limited runs again with a new attempt number.

SSE events during a background scan run: `PhaseStarted`, `PhaseCompleted`, `PhaseFailed`, `PhaseRateLimited`, `RunRateLimited`.

### Resume mechanics

Both triage and scan expose resume endpoints that accept a new billing method. The resume path records the new attempt against the same run id; prior attempts are preserved as history.

CLI example:

```
tally --project NAME --command scan --resume RUN_ID --interaction-mode background --billing-method api
```

Interactive resume is also supported, but no billing-method flag is accepted in that case; the user drives Claude Code themselves and the local `claude` binary handles auth.

---

## Docker-sandboxed Agent SDK runs (TAL-266)

Non-interactive triage and scan runs on the `claude_sdk` provider execute inside the `sdk-sidecar` container generated by `application/triage/compose.py`, not on the host. The SDK runs with `bypassPermissions` so it never stalls on a tool prompt, which is only acceptable because the container is the boundary.

### Container posture

- Read-only root filesystem, all Linux capabilities dropped, `no-new-privileges` set, non-root `agent` user.
- Repo mounts under `/workspace/repos/<name>` are read-only.
- Credentials: OAuth files are bind-mounted read-only (`/home/agent/.claude.json`, `/home/agent/.claude/.credentials.json`). The API key is injected as the `ANTHROPIC_API_KEY` environment variable on the agent service only.
- Egress goes through a tinyproxy allowlist. Triage allows `api.anthropic.com:443` only. Scans add `host.docker.internal:<mcp-port>` so the in-container SDK can reach the Tally MCP server on the host. The compose generator sets `extra_hosts: host.docker.internal:host-gateway` on the agent service, which Linux needs to resolve that name.

### Relay protocol

The host drives one long-lived `docker compose exec -T sdk-sidecar sdk-runner` process. It writes one JSON job spec per request to the exec's stdin. The container emits typed JSONL events (`assistant_text`, `tool_use`, `result`, `error`, `end`) on stdout, and the host consumes only those events. A job's error is confined to that job; the loop continues until the host closes stdin. The triage verdict travels as a typed `result` event rather than free text on stdout.

### Operator steps

- Build the image: `docker build -t tally/triage-agent docker/triage-agent/`. The triage commands build it automatically when it is missing. For the e2e test, build `tally-triage-agent:test` instead.
- Smoke test: `echo '' | docker run --rm -i tally-triage-agent:test sdk-runner` should exit cleanly on stdin EOF.
- End-to-end test: `DOCKER=1 .venv/bin/pytest tests/integration/sdk_relay/ -v`.
- The `sdk-sidecar` container must be running before `docker compose exec` works. The triage commands bring the compose stack up (`ensure_triage_containers`). The background scan launcher does not, so run `docker compose up -d sdk-sidecar` against the generated compose file before the first background scan.

### Troubleshooting

- A missing image fails the first exec with a message naming the build command.
- An exec failure that mentions the service not running means the sidecar is down; start it as above.
- On Linux, a scan that cannot reach the MCP server usually means the `host-gateway` entry is missing from a stale compose file. Regenerate it by restarting the triage stack.

### Known security debts

- The scope-guard PreToolUse hook (loaded in the CLI path) is not loaded in the SDK path. Needs a follow-up ticket.
- The sidecar is shared across runs, so bearer tokens are visible to anything inside the container. Mitigations are per-run token mint and revoke, the container boundary, and serial job execution. That is acceptable for the current threat model; a dedicated container per run is a redesign.
- The CLI `--api-key-override` flag still exposes the key in shell history and `ps`.
- MCP HTTP transport is cleartext on loopback, passing through the tinyproxy allowlist.
- The tinyproxy allowlist is a cross product of hosts and ports. `_validate_mcp_endpoint` narrows it but does not pin exact host:port pairs. A full fix needs squid or a socat forwarder.

---

## Compliance note

Tally never reads `~/.claude/*.json` or any OAuth credential file. The `claude` binary and the Agent SDK own credential storage, format, and lifecycle entirely. Tally interacts with the OAuth path through only two channels:

1. The `claude auth status` subprocess probe. Tally reads the exit code, not the contents of any credential file.
2. The `CLAUDE_CODE_OAUTH_TOKEN` environment variable. Tally reads this value only to decide whether plan billing is available; it does not persist or forward the value anywhere.

Tally controls which environment variables the Agent SDK child process inherits (specifically whether `ANTHROPIC_API_KEY` is present), which determines whether the subprocess uses OAuth or API billing. That is the only control Tally exerts over credential selection.

---

## See also

- [configuration.md](configuration.md) for the `claude.default_billing_method` field and other config knobs.
- [triage.md](triage.md) for triage interaction modes and auto-failover specifics.
- [claude-code-scanning.md](claude-code-scanning.md) for background scan mode and resume.
- [cli.md](cli.md) for the full CLI flag reference.
- [repl.md](repl.md) for the REPL commands.
