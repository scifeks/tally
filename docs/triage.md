# Triage

## Overview

Triage uses an AI agent to assess SAST and API findings from your scans. The agent
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

Run triage on all untriaged SAST and API findings in the active project:

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

### Batch-only mode

```
[acme-audit]> triage --batch
Created 3 batches
```

Creates triage batches from untriaged findings without starting containers or
invoking the agent. Use this to preview how findings will be grouped before
committing to a full triage run.

### Dry-run mode

```
[acme-audit]> triage --dry-run
Rendered 3 batch prompt(s); see DEBUG log
```

Creates batches and renders the prompts that would be sent to the agent, writing
them to the DEBUG log. No containers are started and no agent is invoked. Use this
to inspect prompt construction or debug rendering issues.

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

**Filesystem isolation.** The agent can only access repositories mounted into the
container at `/workspace/repos/`. All other host files are invisible. Credential
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

### What to expect

In proof-of-concept testing with 6 SAST findings across both backends:

- Claude Code (Sonnet): 6/6 format adherence, 37-second median per finding
- OpenCode (Qwen3-Coder-30B): 5/6 format adherence, 20-second median per finding
  (one finding timed out at 120 seconds)
- The two backends fully agreed on 1 of 5 findings where both produced results

Running both backends on the same findings will produce different results. This is
expected. The frontier model is more aggressive about identifying false positives
when data-flow evidence supports it, while the local model tends toward more
conservative assessments.

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
