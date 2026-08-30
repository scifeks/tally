# Triage

## Overview

Triage uses an AI agent to assess SAST, API, and DAST findings from your scans. The agent
reads the finding metadata and the associated source file, then produces a
**verdict** with confidence level, severity, finding type, reasoning, remediation
guidance, attack vector, and call stack. SCA findings are not triaged because they
already reference confirmed CVEs from advisory databases.

Two backends are supported:

- **Claude Code** connects to the Anthropic API using a hosted model (Sonnet by
  default).
- **OpenCode** connects to a local Ollama instance running any compatible model.

Both backends run inside a Docker container with filesystem and network sandboxing.
The agent receives the finding and source content inline, produces a structured JSON
verdict, and exits. No persistent agent state is kept between findings.

Triage can also be started from the web UI. The Triage page shows batch progress in real time and lets you resume failed runs. See [docs/web-ui.md](web-ui.md) for the UI walkthrough.

---

## Prerequisites

- **Docker** installed and running on the host
- `triage_inference` configured in `config/global.json` with a valid provider
- Credentials configured for your chosen backend (see [Host Setup](#host-setup))
- At least one completed scan with untriaged findings

---

## Host Setup

### Claude Code with API key

Set `claude.api_key` in `config/global.json` or export `ANTHROPIC_API_KEY` as an
environment variable. When `claude.api_key` is non-empty, Tally injects it as
`ANTHROPIC_API_KEY` into the container. No host file mounts are needed.

```json
{
  "claude": {
    "api_key": "sk-ant-..."
  },
  "triage_inference": {
    "provider": "claude"
  }
}
```

### Claude Code with OAuth

When `claude.api_key` is empty, Tally falls back to **OAuth mode**. Run `claude`
on the host to authenticate before your first triage run. Tally mounts two
credential files read-only into the container:

- `~/.claude.json` (account identity)
- `~/.claude/.credentials.json` (OAuth tokens)

If either file is missing, compose generation fails with a message directing you
to authenticate on the host or set an API key.

The container cannot persist refreshed tokens to disk because the mount is
read-only. For short triage calls (30-60 seconds per finding), in-memory refresh
is sufficient. If you see authentication errors, re-run `claude` on the host to
refresh the session.

### Local Model (Ollama / Llama.cpp)

Add a `triage_inference` block referencing your local provider. The `base_url`
from the provider block determines the network egress allowlist; the triage
container can only reach the specified endpoint.

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:14b"
  },
  "triage_inference": {
    "provider": "ollama",
    "model": "qwen3-coder:30b"
  }
}
```

The `model` override in `triage_inference` selects a different model than the
provider default. All other provider fields (base_url, timeout) are inherited
unless explicitly overridden.

> **Note:** If Ollama runs on `localhost`, Tally rewrites the URL to
> `host.docker.internal` in the compose file so the container can reach the host
> network.

---

## Running Triage

Run triage on all untriaged SAST, API, and DAST findings in the active project:

```
[acme-audit]> triage

Warning: prompt injection risk
Triage reads source files and findings from scanned repositories
and includes that content verbatim in prompts sent to an LLM.
Malicious content in those files could manipulate the model into
writing incorrect triage results or reading sensitive files.

Only proceed if you trust the repositories in this project.

Proceed with triage? [y/N]: y
Building triage agent image (this may take a few minutes)...
Triage agent image ready.
Starting triage containers...
Triage containers ready.
Triage: 3 sessions run, 2 success, 1 failed, 0 incomplete
```

The image build message appears only on the first run. On later runs, containers
start within a few seconds if they are not already running.

---

## Container Lifecycle

### First triage run

On the first `triage` call, Tally checks for the `tally/triage-agent` Docker image.
If the image does not exist, Tally builds it automatically. The image is based on
Debian 12 slim and includes Claude Code, OpenCode, tinyproxy, and git. Building
takes a few minutes depending on network speed.

After the image is ready, Tally generates a `docker-compose.yaml` for the active
project and starts two services: the triage agent and a tinyproxy sidecar for
network egress control.

### Project switch

Running `project switch <name>` tears down any running triage containers. This is
best-effort; errors during teardown are silently ignored.

Containers do **not** auto-restart on the new project. The next `triage` call
regenerates the compose file for the now-active project (with that project's
repository mounts and credentials) and starts fresh containers.

### Manual rebuild

```
[no-project]> triage --rebuild-container
Stopping triage agent containers...
Triage agent image rebuilt.
```

`triage --rebuild-container` stops running containers and rebuilds the Docker image
from scratch. No active project is required. Use this when:

- The Dockerfile has been updated
- The image is corrupted or in an inconsistent state
- You want to pick up new versions of Claude Code or OpenCode

The next `triage` call starts containers from the rebuilt image.

---

## Security Model

### What the sandbox protects against

**Filesystem isolation.** The agent runs with a working directory and file access
scope limited to `/workspace`. Repositories are mounted into the container at
`/workspace/repos/`, and the agent CLI tools (for Claude Code and OpenCode) are
invoked with `--add-dir /workspace` or `--dir /workspace` flags, restricting all
file operations to that subtree. All other host files are invisible. Credential
files (when using OAuth mode) are mounted read-only.

**Network restriction.** A tinyproxy sidecar running in FilterDefaultDeny mode
restricts outbound traffic. For Claude Code, only `api.anthropic.com:443` is
reachable. For OpenCode, only the configured Ollama endpoint is reachable. All
other connections are refused.

**Privilege limitation.** The container runs as a non-root `agent` user with all
Linux capabilities dropped, privilege escalation blocked, and a read-only root
filesystem. Temporary writes go to tmpfs mounts at `/tmp` and
`/home/agent/.claude`.

### What the sandbox does not protect against

**Repository content.** The agent can read and write files inside mounted
repositories. If the agent is compromised or manipulated by prompt injection, it
could modify repository files.

**LLM data exposure.** Finding metadata and source file contents are sent to the
configured LLM endpoint (Anthropic API for Claude Code, Ollama for OpenCode). The
sandbox does not prevent this; it is the intended data flow.

**Prompt injection.** Source files and finding metadata are included verbatim in
prompts. Malicious content in those files could influence the agent's triage
verdicts. Run `triage --dry-run` to inspect what would be sent before running a
full triage. The prompt injection warning displayed before each triage run
reminds you of this risk.

### Network policy detail

Two Docker networks enforce the egress allowlist:

- `triage-internal` is an internal network with no external connectivity. The
  agent container connects only to this network.
- `triage-external` provides internet access. Only the tinyproxy sidecar connects
  to both networks.

The proxy uses a filter file that allowlists specific hostnames. For Claude Code,
the filter allows `api.anthropic.com` on port 443. For OpenCode, the filter allows
the host and port parsed from the provider's `base_url`.

---

## Accuracy: Local vs. Frontier

### Frontier model (Claude Code)

Claude Code invokes a hosted Anthropic model (Sonnet by default, configurable via
`claude.model` in `config/global.json`). Frontier models produce more accurate
verdicts, particularly for findings that require data-flow analysis, recognizing
sanitization patterns, or evaluating framework-level protections. Requires network
access to `api.anthropic.com` and an Anthropic API key or authenticated OAuth
session.

### Local model (OpenCode)

OpenCode connects to a local Ollama instance. Verdict quality depends on the model
you run. Smaller models (such as Qwen3-Coder-30B) produce more conservative
verdicts and are more likely to miss subtle sanitization or protection patterns.
No finding data leaves your network.

### Batching differences

Claude Code processes up to 4 findings per batch. Local models (Ollama and
Llama.cpp) use a batch size of 1 (one finding per agent invocation) because
smaller models perform better with isolated analysis tasks. This means a scan
with 100 SAST findings will result in 25 agent invocations for Claude Code but
100 for OpenCode. Batching is automatic and cannot be overridden.

---

## DefectDojo Sync

Triage results can be automatically synced to DefectDojo after each
triage run. Set `post_triage_sync` to `["defectdojo"]` in
`config/global.json`. See
[docs/integrations/defect-dojo.md](integrations/defect-dojo.md#automatic-post-triage-sync)
for setup details.

---

## MCP Triage Mode

MCP triage mode allows you to run interactive triage through Claude Code. Each batch of findings is triaged by Claude, then presented to you for review and approval before the verdicts are saved to the project database.

### How MCP triage differs from auto-triage

**Auto-triage** (headless mode) runs the triage agent inside a Docker container and saves all verdicts automatically without user intervention. Findings are processed in configurable batch sizes.

**MCP triage** (interactive mode) operates as an MCP server. An external client (Claude Code) connects, streams batches to the agent, and awaits your confirmation on each batch before persisting results. No Docker container runs on the host; the agent executes in Claude Code's environment. Use MCP triage when you want to review findings interactively before accepting triage verdicts.

### Setup

#### Step 1: Generate an MCP token

Generate a bearer token for server authentication in the REPL:

```
[myproject]> mcp token create ci-agent
MCP token created: tly_abc123...xyz
Token name: ci-agent
Warning: Copy this token now. It will not be shown again.
```

Save the token securely. You will pass it to Claude Code when configuring the MCP connection.

#### Step 2: Start the MCP server

Start the MCP triage server from the REPL:

```
[myproject]> tally mcp serve
```

The server starts on the configured `mcp.port` (default: `8765`). To use a different port:

```
[myproject]> tally mcp serve --port 9000
```

The server remains running and awaits connections from Claude Code.

### Claude Code Connection

When you run `mcp serve`, Tally writes a `.mcp.json` file to the
project root if one does not already exist. This file tells Claude Code
where the Tally MCP server is. The URL is built from `mcp.host` and
`mcp.port` in `config/global.json`.

You can also create it manually:

```
[project]> mcp server create
```

The generated file looks like:

```json
{
  "mcpServers": {
    "tally": {
      "type": "sse",
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

#### Step 3: Configure Claude Code

In Claude Code, configure the MCP connection to your Tally instance:

1. Open Claude Code settings
2. Add an MCP server with:
   - **Host:** localhost or your Tally server address
   - **Port:** `8765` (or the port you specified in step 2)
   - **Token:** paste the token from step 1

#### Step 4: Invoke triage in Claude Code

Use the `/tally-triage` slash command in Claude Code:

```
/tally-triage
```

Claude Code connects to the MCP server, retrieves untriaged findings, streams them through the triage agent, and presents each batch to you for confirmation.

### Batch confirmation workflow

When you invoke `/tally-triage`, Claude Code:

1. Fetches untriaged SAST, API, and DAST findings from your active project
2. Groups findings into batches
3. Sends each batch to the triage agent
4. Displays the verdicts and waits for your approval
5. On approval, persists the verdicts to the project database
6. Moves to the next batch

You can approve, reject, or edit verdicts in Claude Code before confirming. Rejected batches are skipped and remain untriaged; you can retry them later.

### When to use MCP triage vs auto-triage

Use **MCP triage** when:
- You want to review and confirm findings interactively before committing verdicts
- You prefer to run triage from Claude Code alongside other development workflows
- You want visibility into each batch before persistence
- You do not want a long-running container on the host

Use **auto-triage** when:
- You want to process all findings headlessly without interaction
- You want triage to run from the REPL or web UI in a fully automated pipeline
- You are triaging a large volume of findings and interactivity is not needed

---

## DAST Triage

DAST (dynamic application security testing) triage differs from SAST triage in one fundamental way: it assumes the vulnerability exists. A dynamic scanner such as ZAP or Burp has already confirmed the behavior by sending a crafted request and observing a vulnerable response. The triage agent's task is to locate the vulnerable code path in the source tree.

Unlike SAST triage, which asks "is this a real vulnerability?", DAST triage asks a different question: "where is the vulnerability in the source code that allows this endpoint to be exploited?" This inverted approach focuses investigation on finding the code, not re-confirming the scanner's observation. The resulting verdict includes a `call_stack` field that traces the full vulnerability chain from request intake to the vulnerable operation.

### Evidence differences between ZAP and Burp

ZAP and Burp provide different evidence in their findings:

**ZAP** includes:
- Alert name and severity
- Attack payload (the malicious input sent by the scanner)
- Parameter name (the injection point)
- Evidence string (proof of behavior extracted from the response)

**Burp** includes:
- Alert name, severity, and confidence
- Full HTTP request and response (decoded and human-readable)
- Vulnerability fingerprint type (identifies the specific variant detected)
- Remediation guidance (vendor-provided fix recommendations)

The triage agent reads both formats and extracts the evidence needed to guide source code investigation.

### Verdict format for DAST findings

DAST verdicts use the standard triage verdict schema with one required addition:

- `finding_id`, `confidence`, `finding_type`, `severity`, `access_required`, `exploitation_complexity`, `user_interaction`, `reasoning`, `remediation` are the same as SAST verdicts.
- `attack_vector` is the HTTP method, endpoint path, and vulnerable parameter (example: `POST /api/user?id=1 (id parameter)`).
- `call_stack` is required and must be non-empty. A JSON array of strings, each in the format `file:line function_name`, that traces every file and function from request entry to the vulnerable operation.

The `call_stack` field is mandatory and distinguishes DAST verdicts from other finding types. The agent must examine the source tree to populate this field before returning a verdict.

### Source code not examined error

If the agent cannot locate the repository, route handler, or source code for an endpoint, it returns an error object instead of a verdict:

```json
{
  "error": "source_not_examined",
  "finding_id": 12345,
  "reason": "Could not locate route handler for POST /api/endpoint"
}
```

This prevents false positives from incomplete source examination.

---

## Troubleshooting

### "Docker is not installed or not running"

Verify Docker is available:

```bash
docker --version
docker ps
```

If `docker ps` fails, start the Docker daemon.

### "Triage disabled in config"

Add a `triage_inference` block to `config/global.json` with a valid `provider`
(e.g. `"ollama"`, `"llama_cpp"`, or `"claude"`). Triage is disabled when this
block is absent.

### Image build fails

Check your network connectivity. The Dockerfile pulls base image layers from
Docker Hub and installs Claude Code and OpenCode from their public install
scripts. If the build fails partway through:

```
[acme-audit]> triage --rebuild-container
```

To clear Docker's build cache before retrying:

```bash
docker builder prune
```

### Containers do not restart after project switch

This is expected. `project switch` tears down triage containers. Run `triage` on
the new project to start fresh containers with the correct repository mounts.

### "Another triage is in progress"

Only one triage session can run per project at a time. Wait for the current
session to finish, then retry.
