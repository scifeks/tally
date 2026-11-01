"""One-shot prompt renderer for DAST findings (ZAP, Burp)."""

from __future__ import annotations

from typing import Any

from application.triage.prompts._fencing import (
    DECISION_REMINDER,
    FENCING_PREAMBLE,
    fence,
)
from application.triage.prompts._severity import format_severity
from application.triage.prompts.triage_prompt import TriagePrompt

# Raw HTTP request/response pairs run longer than other fields.
_EVIDENCE_MAX_CHARS = 16000


def compose(
    finding: dict[str, Any],
    *,
    project: str,
) -> TriagePrompt:
    """Build a one-shot triage prompt for a DAST finding."""
    tool = finding.get("tool") or "unknown"

    preamble = [
        _PREAMBLE,
        FENCING_PREAMBLE,
        (
            "## Task\n\n"
            "Triage the DAST finding in the Finding Record for "
            f"project `{project}`. The scanner "
            "confirmed this behavior by sending a "
            "request and observing the response. Your "
            "job is to locate the vulnerable code path "
            "in the source tree."
        ),
    ]
    finding_data = [
        "## Finding Record\n\n" + fence(_metadata(finding, tool), "finding_metadata"),
        _build_evidence_section(finding),
    ]
    guidance = [
        _SOURCE_INVESTIGATION,
        _VULNERABILITY_ANALYSIS,
        _PREDICATE_GUIDANCE,
        DECISION_REMINDER,
        _output_schema(finding["id"]),
    ]
    return TriagePrompt(
        preamble="\n\n".join(preamble),
        finding_data="\n\n".join(finding_data),
        guidance="\n\n".join(guidance),
    )


def render(finding: dict[str, Any], *, project: str) -> str:
    """Build the prompt as a single message."""
    return compose(finding, project=project).combined()


# Private helpers


def _metadata(finding: dict[str, Any], tool: str) -> dict[str, object]:
    record: dict[str, object] = {
        "finding_id": finding["id"],
        "tool": tool,
        "alert_name": finding.get("alert_name"),
        "severity": format_severity(finding.get("severity")),
        "confidence": finding.get("confidence"),
        "method": finding.get("method"),
        "url": finding.get("url"),
        "description": finding.get("description"),
        "cwe_id": finding.get("cwe_id"),
        "risk_type": finding.get("risk_type"),
        "search_root": _search_root(finding.get("repo")),
    }
    if tool == "zap":
        record["param"] = finding.get("param")
        record["attack"] = finding.get("attack")
    elif tool == "burp":
        record["remediation"] = finding.get("remediation")
        record["fingerprint_type"] = finding.get("fingerprint_type")
    return record


def _build_evidence_section(
    finding: dict[str, Any],
) -> str:
    evidence = finding.get("evidence")
    if not evidence:
        return "## HTTP Evidence\n\nNo HTTP evidence available for this finding."
    return "## HTTP Evidence\n\n" + fence(
        {"evidence": str(evidence)},
        "http_evidence",
        max_chars=_EVIDENCE_MAX_CHARS,
    )


def _search_root(repo: str | None) -> str:
    return f"/workspace/repos/{repo}/" if repo else "/workspace/repos/"


# Static prompt text

_SOURCE_INVESTIGATION = """\
## Source Investigation

The endpoint under test is the `method` and `url` in the Finding Record
(assume GET when `method` is null). Search under the `search_root` given
there.

Complete these steps before issuing a verdict:

1. Locate the route handler that serves this endpoint. Search for route
   definitions, URL patterns, or framework entry points matching the URL
   path.
2. Read the handler and trace every code path the request data passes
   through: controllers, services, models, middleware, and template
   rendering.
3. Identify where the vulnerability exists in the code. The scanner proved
   the endpoint is exploitable; find the code that allows it.
4. Trace the full chain: which files and functions are involved, from
   request intake to the vulnerable operation. Report each link in the
   call_stack field.

If you cannot locate the route handler or source code, return a
source_not_examined error instead of a verdict."""

_PREAMBLE = """\
You are a web application security analyst performing \
automated triage of a DAST (dynamic application \
security testing) finding.
You have read-only access to the full source tree \
under /workspace/repos/.
Use your read, grep, and glob tools to examine source \
files as needed.
This session is NON-INTERACTIVE. You must complete all \
work and exit.
Do NOT ask questions. Do NOT wait for input. Finish \
and exit."""

_VULNERABILITY_ANALYSIS = """\
## Vulnerability Analysis

The dynamic scanner exploited this endpoint with a \
crafted payload. The vulnerability is proven. Your \
job is to locate the code that permits it.

Complete the Source Investigation steps above BEFORE \
reading further. If you could not locate the relevant \
source code, return a source_not_examined error:
{"error": "source_not_examined", "finding_id": <id>, \
"reason": "<why>"}

For every finding, answer each question in your \
`reasoning` field:

**1. Where is the vulnerable code?**
   Name the file, function, and line where the \
vulnerability originates. If the vulnerability spans \
multiple locations (missing validation in file A, \
unsafe execution in file B), identify each link in \
the chain.

**2. What code deficiency permits the exploit?**
   Identify the specific missing control: absent \
input validation, missing output encoding, lack of \
parameterized queries, missing authentication or \
authorization checks, or other defensive gaps. Trace \
the data flow from the request handler to the \
vulnerable operation.

**3. Are there mitigations that affect severity?**
   Check for framework-level protections, middleware, \
WAF rules, authentication requirements, or input \
validation that could reduce the impact or \
exploitability of the confirmed vulnerability. \
These are only visible in the source.

**4. What is the full vulnerability chain?**
   List every file and function involved in the \
vulnerable path, from request intake to the point \
of exploitation. This becomes the call_stack in \
your verdict."""


def _output_schema(finding_id: int) -> str:
    return f"""\
## Output

When your verdict is ready, use the write tool to \
write the JSON object to `/workspace/out/verdict.json`.\
 The file MUST contain only the JSON object - no \
markdown fences, no commentary, no leading or trailing \
whitespace. Anything you say in chat is ignored; only \
the file contents are read.

Schema for verdict.json:

{{"finding_id": {finding_id}, "confidence": \
"confirmed", \
"finding_type": "<vulnerability|weakness\
|misconfiguration|exposure|dependency|informational\
|secret>", "severity": "<critical|high|medium|low\
|informational>", "access_required": \
"<none|authenticated|privileged>", \
"exploitation_complexity": "<low|high>", \
"user_interaction": "<none|required>", "reasoning": \
"<one paragraph addressing all four vulnerability \
analysis questions>", "remediation": "<one specific, \
actionable fix>", "attack_vector": "<HTTP method + \
path + parameter, or n/a>", "call_stack": \
["file:line function", ...]}}

Constraints:
- `finding_id` MUST equal {finding_id}.
- `confidence` MUST be `confirmed`. The scanner \
proved the vulnerability exists.
- `call_stack` MUST be a non-empty JSON array of \
strings tracing the vulnerability chain from request \
intake to the vulnerable operation. Each entry should \
be "file:line function_name". If you cannot trace \
the chain, explain why in the reasoning field and \
provide your best partial trace.
- All string fields MUST be present.
- `access_required`: none (unauthenticated), \
authenticated (valid session), privileged \
(admin/root/DBA).
- `exploitation_complexity`: low (straightforward \
exploit), high (requires chaining, race conditions, \
or non-default config).
- `user_interaction`: none (no victim action needed), \
required (victim must click a link, open a file, or \
perform some action).
- Predicates must be mutually consistent (see \
Predicate Guidance).
- Output the JSON, then stop. Do NOT continue \
producing text."""


_PREDICATE_GUIDANCE = """\
## Predicate Guidance

The access_required, exploitation_complexity, \
user_interaction, severity, and finding_type fields \
are orthogonal dimensions. Each must be assigned \
independently based on evidence, then checked for \
mutual consistency.

- access_required: What access level must an attacker \
already have?
  none = unauthenticated network access suffices.
  authenticated = attacker needs a valid user session.
  privileged = attacker needs admin, root, or DBA \
access.

- exploitation_complexity: How complex is the exploit?
  low = straightforward single-step exploit with \
public techniques.
  high = requires chaining multiple conditions, race \
windows, non-default configuration, or specialized \
knowledge.

- user_interaction: Does the victim need to do \
something?
  none = no victim action needed; attacker exploits \
directly.
  required = victim must click a link, open a file, \
visit a page, or perform some other action.

Consistency rules (verdict will be rejected if \
violated):
- informational finding_type requires severity <= \
medium.
- severity MUST be greater than informational.
- Two or more of (privileged access, high complexity, \
required user interaction) precludes critical \
severity.
- weakness finding_type precludes critical severity."""
