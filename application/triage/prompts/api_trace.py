"""One-shot prompt renderer for ZAP/dynamic-analysis findings."""

from __future__ import annotations

from typing import Any

from application.triage.prompts._fencing import (
    FENCING_PREAMBLE,
    POST_DATA_REMINDER,
    fence,
)
from application.triage.prompts._severity import format_severity


def render(
    finding: dict[str, Any],
    *,
    project: str,
) -> str:
    """Build a self-contained one-shot triage prompt."""
    finding_id = finding["id"]

    task = f"## Task\n\nTriage the following ZAP/dynamic-analysis \
finding for project `{project}`."
    metadata_fenced = "## Finding Record\n\n" + fence(
        _format_metadata(finding), "finding_metadata"
    )

    sections: list[str] = [
        _PREAMBLE,
        FENCING_PREAMBLE,
        task,
        metadata_fenced,
        POST_DATA_REMINDER,
        _EPISTEMIC_CONSERVATISM,
        _CONFIDENCE_GUIDANCE,
        _PREDICATE_GUIDANCE,
        _output_schema(finding_id),
    ]
    return "\n\n".join(sections)


# -- private helpers --------------------------------------------------


def _format_metadata(finding: dict[str, Any]) -> str:
    sev = format_severity(finding.get("severity"))
    fid = finding["id"]
    lines: list[str] = [
        f"- finding_id   : {fid}",
        f"- tool         : {_val(finding, 'tool')}",
        f"- alert_name   : {_val(finding, 'alert_name')}",
        f"- severity     : {sev}",
        f"- method       : {_val(finding, 'method')}",
        f"- url          : {_val(finding, 'url')}",
        f"- param        : {_val(finding, 'param')}",
        f"- evidence     : {_val(finding, 'evidence')}",
        f"- cwe_id       : {_val(finding, 'cwe_id')}",
        f"- risk_type    : {_val(finding, 'risk_type')}",
        f"- description  : {_val(finding, 'description')}",
        f"- remediation  : {_val(finding, 'remediation')}",
    ]
    return "\n".join(lines)


def _val(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if v is None:
        return "n/a"
    return str(v)


# -- static prompt text -----------------------------------------------

_PREAMBLE = """\
You are a web application security analyst performing automated triage.
This session is NON-INTERACTIVE. You must complete all work and exit.
Do NOT ask questions. Do NOT wait for input. Finish and exit."""

_EPISTEMIC_CONSERVATISM = """\
## Epistemic Conservatism

This is the most important section. Read it carefully before assigning
any confidence level.

- Do NOT upgrade a finding's severity or confidence without concrete
  evidence of exploitability.
- Do NOT mark a finding `confirmed` unless the ZAP evidence clearly
  demonstrates a real vulnerability (e.g., SQL error in response,
  unencoded reflected script tag).
- When uncertain, prefer `potential` over `probable`, and `probable`
  over `confirmed`.

ZAP alerts match dynamic scan patterns. The alert name (e.g. `SQL
Injection`, `Cross Site Scripting`) reflects the test category, not
a confirmed vulnerability class. You must independently determine the
actual risk.

For any finding, explicitly answer each question in your `reasoning`
field:

**1. Is the ZAP evidence a true positive or a scanner artifact?**
   For example, reflected text that is HTML-encoded is not XSS. Check
   whether the evidence string represents actual exploitation or a
   scanner-generated test artifact.

**2. Does the URL pattern and parameter suggest a real attack surface?**
   Is the parameter user-controllable? Is it processed by the backend?
   Or is it a static value, a configuration parameter, or not consumed?

**3. Does the application framework likely provide automatic protection?**
   For example, parameterized queries by default, CSRF middleware, or
   automatic encoding of output. Many frameworks provide layers of
   defense that ZAP cannot detect.

**4. Is there a meaningful, attacker-observable outcome?**
   Can the attacker tell the difference between success and failure?
   If the exploit path and normal path produce identical responses,
   there is no practical vulnerability."""


def _output_schema(finding_id: int) -> str:
    return f"""\
## Output

Emit ONE strict JSON object on a single line. No code fences. No prose
before or after. No markdown. No leading whitespace. Schema:

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

- confirmed: The ZAP evidence clearly demonstrates exploitability
  (e.g., SQL error in response, reflected unencoded script tag in HTML
  output). The parameter is controllable, the code is vulnerable, and
  the attacker can observe a meaningful outcome.
- probable: Evidence strongly suggests vulnerability but is not
  conclusive. For example, timing-based detection of SQL injection,
  indirect indicators of exploitation, or patterns consistent with
  vulnerable code but without direct proof.
- potential: The alert is plausible but evidence is weak or indirect.
  Dynamic scanners produce false positives at high rates. This is the
  safe default when evidence is ambiguous or the framework likely
  provides automatic protection.
- false_positive: The alert pattern is a known false positive. For
  example, reflected but HTML-encoded output, informational headers
  missing from response, or ZAP pattern match unrelated to the tested
  parameter."""


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
