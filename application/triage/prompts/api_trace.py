"""One-shot prompt renderer for web security findings."""

from __future__ import annotations

from typing import Any

from application.triage.prompts._fencing import (
    DECISION_REMINDER,
    FENCING_PREAMBLE,
    fence,
)
from application.triage.prompts._severity import format_severity
from application.triage.prompts.triage_prompt import TriagePrompt


def compose(
    finding: dict[str, Any],
    *,
    project: str,
) -> TriagePrompt:
    """Build a one-shot triage prompt for a web security finding."""
    preamble = [
        _PREAMBLE,
        FENCING_PREAMBLE,
        "## Task\n\nTriage the web security finding in the Finding Record "
        f"for project `{project}`.",
    ]
    guidance = [
        _SOURCE_INVESTIGATION,
        _EPISTEMIC_CONSERVATISM,
        _CONFIDENCE_GUIDANCE,
        _PREDICATE_GUIDANCE,
        DECISION_REMINDER,
        _output_schema(finding["id"]),
    ]
    return TriagePrompt(
        preamble="\n\n".join(preamble),
        finding_data="## Finding Record\n\n"
        + fence(_metadata(finding), "finding_metadata"),
        guidance="\n\n".join(guidance),
    )


def render(finding: dict[str, Any], *, project: str) -> str:
    """Build the prompt as a single message."""
    return compose(finding, project=project).combined()


# Private helpers


def _metadata(finding: dict[str, Any]) -> dict[str, object]:
    return {
        "finding_id": finding["id"],
        "tool": finding.get("tool"),
        "alert_name": finding.get("alert_name"),
        "severity": format_severity(finding.get("severity")),
        "method": finding.get("method"),
        "url": finding.get("url"),
        "param": finding.get("param"),
        "evidence": finding.get("evidence"),
        "cwe_id": finding.get("cwe_id"),
        "risk_type": finding.get("risk_type"),
        "description": finding.get("description"),
        "remediation": finding.get("remediation"),
    }


# Static prompt text

_SOURCE_INVESTIGATION = """\
## Source Investigation

The endpoint under test is the `method` and `url` in the Finding Record
(assume GET when `method` is null).

You MUST complete these steps before issuing a verdict:

1. Locate the endpoint: search `/workspace/repos/` for route definitions,
   URL patterns, or framework entry points that match the URL path.
2. Read the handler: open the controller, resolver, or handler function
   that processes requests to this endpoint. Understand what the code
   actually does with user input.
3. Identify the behavior the scanner flagged: find the specific code or
   configuration that produces the behavior the scanner reported. For
   configuration findings (introspection, batch limits, security headers),
   locate the config that controls it.
4. Assess exploitability: determine what a bad actor could actually gain.
   A scanner reporting a behavior is not evidence of a vulnerability. You
   must explain the concrete attack scenario against this specific code.

When the flagged behavior is controlled by a third-party library's defaults
(query depth, alias limits, batch limits, complexity caps, introspection,
security headers, CORS), the question is whether the application configures
an override at the point it constructs the library. Locate that construction
site in the application's own source (typically a Server, ServerConfig,
middleware wire-up, or bootstrap file) and inspect the options passed. Do NOT
read the library's implementation under `vendor/` to understand its
internals; treat the library's documented defaults as the baseline and answer
from what the application does or does not override.

If you cannot complete steps 1-3, return a source_not_examined error instead
of a verdict."""

_PREAMBLE = """\
You are a web application security analyst performing \
automated triage.
You have read-only access to the full source tree \
under /workspace/repos/.
Use your read, grep, and glob tools to examine source \
files as needed.
This session is NON-INTERACTIVE. You must complete all \
work and exit.
Do NOT ask questions. Do NOT wait for input. Finish \
and exit."""

_EPISTEMIC_CONSERVATISM = """\
## Epistemic Conservatism

This is the most important section. Read it carefully \
before assigning any confidence level.

A scanner reporting a behavior is not evidence of a \
vulnerability. Before assigning any verdict, you must \
locate the application code that produces the reported \
behavior and determine whether an attacker could \
exploit it for any gain.

Complete the Source Investigation steps above BEFORE \
reading further. If you could not locate the relevant \
source code, return the source_not_examined error now.

- Do NOT upgrade severity or confidence without \
identifying the specific code or configuration that \
causes the reported behavior.
- Do NOT mark a finding `confirmed` unless you can \
describe a concrete attack scenario against the code \
you examined (scanner output alone is NOT sufficient).
- When uncertain, prefer `potential` over `probable`, \
and `probable` over `confirmed`.
- If the source code could not be examined (no files \
at /workspace/repos/ or you could not locate the \
handler), you MUST return an error object instead of \
a verdict:
  {"error": "source_not_examined", "finding_id": <id>, \
"reason": "<why>"}
  Do NOT return a verdict when the source was not \
examined.

For every finding, answer each question in your \
`reasoning` field:

**1. What code produces the reported behavior?**
   Name the file, function, or configuration setting \
you found. If the scanner reported a misconfiguration \
(introspection enabled, missing headers, batch \
queries allowed), identify where it is configured \
and whether the setting is intentional, environment-\
specific, or a default.

**2. What could an attacker actually do?**
   Describe the concrete attack scenario. What input \
would the attacker send? What response or side effect \
would they observe? What do they gain? "The scanner \
found X" is not an attack scenario. If you cannot \
describe a specific exploit path, the finding is \
potential at best.

**3. Are there mitigations the scanner cannot see?**
   Check for framework-level protections, middleware, \
WAF rules, authentication requirements, rate limits, \
input validation, or output encoding that the dynamic \
scanner could not observe. These are only visible in \
the source.

**4. Is the attack surface real or theoretical?**
   Is this a production endpoint or a dev/test route? \
Is the vulnerable parameter actually user-controllable \
or is it server-generated? Does the endpoint require \
authentication or privileges that limit the attack \
surface?"""


def _output_schema(finding_id: int) -> str:
    return f"""\
## Output

When your verdict is ready, use the write tool to write the JSON object to
`/workspace/out/verdict.json`. The file MUST contain only the JSON object -
no markdown fences, no commentary, no leading or trailing whitespace.
Anything you say in chat is ignored; only the file contents are read.

Schema for verdict.json:

{{"finding_id": {finding_id}, "confidence": "<confirmed|probable\
|potential|false_positive>", "finding_type": "<vulnerability|weakness\
|misconfiguration|exposure|dependency|informational|secret>", \
"severity": "<critical|high|medium|low|informational>", \
"access_required": "<none|authenticated|privileged>", \
"exploitation_complexity": "<low|high>", \
"user_interaction": "<none|required>", \
"reasoning": \
"<one paragraph addressing all four risk-assessment questions>", \
"remediation": "<one specific, actionable fix>", "attack_vector": \
"<HTTP method + path + parameter, or n/a>", "call_stack": []}}

Constraints:
- `finding_id` MUST equal {finding_id}.
- `call_stack` MUST be a JSON array (may be empty for API findings).
- All string fields MUST be present. Use empty string only where
  genuinely not applicable.
- `access_required`: none (unauthenticated), authenticated (valid
  session), privileged (admin/root/DBA).
- `exploitation_complexity`: low (straightforward exploit), high
  (requires chaining, race conditions, or non-default config).
- `user_interaction`: none (no victim action needed), required
  (victim must click a link, open a file, or perform some action).
- Predicates must be mutually consistent (see Predicate Guidance).
- Output the JSON, then stop. Do NOT continue producing text."""


_CONFIDENCE_GUIDANCE = """\
## Confidence Guidance

- confirmed: You located the vulnerable code, traced \
user input to the sink, and can describe a concrete \
exploit that an attacker could execute. The source \
confirms the scanner's finding and no mitigations \
neutralize it. ALL conditions must hold.
- probable: The source code strongly suggests a \
vulnerability but you could not complete the full \
trace. For example, the handler processes user input \
unsafely but you could not confirm the absence of \
upstream middleware that sanitizes it.
- potential: The finding is plausible but the source \
investigation introduced significant uncertainty. \
The endpoint exists but the vulnerable code path may \
be unreachable, mitigated by the framework, or \
limited to dev/test environments.
- false_positive: The source code proves the finding \
is safe. The behavior is intentional, the input is \
sanitized, the endpoint is unreachable in production, \
or the scanner misidentified the pattern."""


_PREDICATE_GUIDANCE = """\
## Predicate Guidance

The access_required, exploitation_complexity, user_interaction,
confidence, severity, and finding_type fields are orthogonal
dimensions. Each must be assigned independently based on evidence,
then checked for mutual consistency.

- access_required: What access level must an attacker already have?
  none = unauthenticated network access suffices.
  authenticated = attacker needs a valid user session.
  privileged = attacker needs admin, root, or DBA access.

- exploitation_complexity: How complex is the exploit chain?
  low = straightforward single-step exploit with public techniques.
  high = requires chaining multiple conditions, race windows,
  non-default configuration, or specialized knowledge.

- user_interaction: Does the victim need to do something?
  none = no victim action needed; attacker exploits directly.
  required = victim must click a link, open a file, visit a page,
  or perform some other action for the exploit to succeed.

Consistency rules (your verdict will be rejected if violated):
- false_positive requires severity=low or informational.
- informational finding_type requires severity <= medium.
- confirmed confidence requires severity > informational.
- Two or more of (privileged access, high complexity, required
  user interaction) precludes critical severity.
- weakness finding_type precludes critical severity."""
