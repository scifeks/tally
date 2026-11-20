"""One-shot prompt renderer for SAST (semgrep) findings."""

from __future__ import annotations

import json
import posixpath
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
    output_instruction: str,
) -> TriagePrompt:
    """Build a one-shot triage prompt for a semgrep finding."""
    finding_id = finding["id"]
    source_path = _container_path(finding.get("repo"), finding.get("file"))

    preamble = [
        _PREAMBLE,
        FENCING_PREAMBLE,
        "## Task\n\nTriage the semgrep finding in the Finding Record "
        f"for project `{project}`.",
    ]
    guidance = [
        _source_instructions(source_path),
        _EPISTEMIC_CONSERVATISM,
        _CONFIDENCE_GUIDANCE,
        _PREDICATE_GUIDANCE,
        DECISION_REMINDER,
        _output_schema(finding_id, output_instruction),
    ]
    return TriagePrompt(
        preamble="\n\n".join(preamble),
        finding_data="## Finding Record\n\n"
        + fence(_metadata(finding, source_path), "finding_metadata"),
        guidance="\n\n".join(guidance),
    )


def render(
    finding: dict[str, Any],
    *,
    project: str,
    output_instruction: str,
) -> str:
    """Build the prompt as a single message."""
    return compose(
        finding, project=project, output_instruction=output_instruction
    ).combined()


# Private helpers


def _metadata(finding: dict[str, Any], source_path: str | None) -> dict[str, object]:
    return {
        "finding_id": finding["id"],
        "tool": finding.get("tool"),
        "rule_id": finding.get("rule_id"),
        "severity": format_severity(finding.get("severity")),
        "file": finding.get("file"),
        "source_path": source_path,
        "line_start": finding.get("line_start"),
        "cwe": _format_cwe(finding.get("cwe")),
        "description": finding.get("description"),
        "code_snippet": finding.get("code_snippet"),
        "risk_type": finding.get("risk_type"),
        "owasp": finding.get("owasp"),
    }


def _format_cwe(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return ", ".join(str(c) for c in raw) if raw else None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
        if isinstance(parsed, list):
            joined = ", ".join(str(c) for c in parsed)
            return joined if joined else None
        return str(parsed)
    return str(raw)


def _container_path(repo: str | None, file_path: str | None) -> str | None:
    """Resolve the finding's file inside the repo mount, or None if it escapes."""
    if not repo or not file_path:
        return None
    root = f"/workspace/repos/{repo}/"
    resolved = posixpath.normpath(root + file_path)
    return resolved if resolved.startswith(root) else None


def _source_instructions(source_path: str | None) -> str:
    if source_path is None:
        return (
            "## Source File\n\n"
            "The finding's file could not be resolved inside the repository "
            "(`source_path` is null). Base your analysis on the `code_snippet` "
            "and `description` in the Finding Record."
        )
    return (
        "## Source File\n\n"
        "Read the file at the `source_path` given in the Finding Record, "
        "starting around `line_start` when it is set. Trace imports, check "
        "framework configs, and follow the data flow from user input to the "
        "sink."
    )


# Static prompt text

_PREAMBLE = """\
You are a web application security analyst performing automated triage.
You have read-only access to the full source tree under /workspace/repos/.
Use your read tool to examine source files as needed.
This session is NON-INTERACTIVE. You must complete all work and exit.
Do NOT ask questions. Do NOT wait for input. Finish and exit."""

_EPISTEMIC_CONSERVATISM = """\
## Epistemic Conservatism

This is the most important section. Read it carefully before assigning
any confidence level.

Before assigning any verdict, use the read tool to examine the file at
`source_path` in the Finding Record. Do not rely solely on the
code_snippet from the finding metadata.

- Do NOT upgrade a finding's severity or confidence without concrete
  evidence in the code path.
- Do NOT mark a finding `confirmed` unless you can trace user input
  to the sink through real, executing code (an AST data-flow match
  alone is NOT sufficient).
- When uncertain, prefer `potential` over `probable`, and `probable`
  over `confirmed`.
- If the source file could not be read, you MUST return an error
  object instead of a verdict:
  {"error": "source_not_examined", "finding_id": <id>, "reason": "<why>"}
  Do NOT return a verdict when the source was not examined.

For any finding involving user-supplied input, explicitly answer each
question in your `reasoning` field:

**1. Does user input actually reach the sink at runtime?**
   Is the code reachable? Is it dead code, a dev-only entrypoint, or
   conditionally compiled/included? Is the file part of the production
   request lifecycle? (e.g. Laravel's server.php is the dev shim, not
   used in production.)

**2. Does the runtime environment pre-process the input?**
   For URI/path findings: HTTP servers normalize paths BEFORE
   populating $_SERVER['REQUEST_URI']. Sequences like `/../` are
   resolved at the HTTP layer. Confirm whether traversal sequences
   survive to the application. For header findings: proxies may strip
   or rewrite headers. For body findings: middleware or WAFs may
   transform values.

**3. Does the sink actually cause harm, or only observe input?**
   `file_exists($path)` discloses existence but does not read content.
   Be precise about what the attacker gains, not just that tainted
   data touched a dangerous function.

**4. Is there a meaningful, attacker-observable outcome?**
   Can the attacker tell the difference between success and failure?
   If exploit path and normal path produce identical responses, there
   is no practical vulnerability even if code is reachable.

Semgrep rules match syntactic or dataflow patterns. The rule label
(e.g. `tainted-filename`, `ssrf`) reflects the pattern family, not a
confirmed vulnerability class. You must independently determine the
actual risk. Examples of common misclassifications:
- `tainted-filename` on `file_exists()` is an existence oracle, not
  arbitrary file read/write.
- `ssrf` on `parse_url(..., PHP_URL_PATH)`: PHP_URL_PATH strips
  scheme and host; network SSRF is not achievable via this extraction.
- `xss` on a value echoed into a JSON response is not XSS.
Always re-derive the vulnerability class from the code, not the rule."""


def _output_schema(finding_id: int, output_instruction: str) -> str:
    return f"""\
{output_instruction}

Schema for the verdict JSON object:

{{"finding_id": {finding_id}, "confidence": "<confirmed|probable\
|potential|false_positive>", "finding_type": "<vulnerability|weakness\
|misconfiguration|exposure|dependency|informational|secret>", \
"severity": "<critical|high|medium|low|informational>", \
"access_required": "<none|authenticated|privileged>", \
"exploitation_complexity": "<low|high>", \
"user_interaction": "<none|required>", \
"reasoning": \
"<one paragraph addressing all four runtime-layer questions>", \
"remediation": "<one specific, actionable fix>", "attack_vector": \
"<HTTP method + path + parameter, or n/a>", "call_stack": \
["file:line function", ...]}}

Constraints:
- `finding_id` MUST equal {finding_id}.
- `call_stack` MUST be a (possibly empty) JSON array of strings.
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

- confirmed: You traced user input to the vulnerable sink through
  real, production code; runtime preprocessing does not neutralize
  the payload; the sink causes demonstrable harm; and the attacker
  can observe a meaningful outcome. ALL FOUR conditions must hold.
- probable: The pattern strongly suggests a vulnerability but you
  could not complete the full trace. Runtime preprocessing is
  unlikely to neutralize the input.
- potential: The finding is plausible but one or more of the four
  runtime layers introduces significant uncertainty. Includes cases
  where the entrypoint is dev-only, the sink effect is weak, or
  HTTP normalization likely collapses the payload.
- false_positive: The flagged pattern is safe in context (sanitized,
  constant value, dead code, upstream normalization fully neutralizes
  input, or the semgrep rule is misclassified)."""


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
