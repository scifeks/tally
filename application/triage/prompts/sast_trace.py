"""One-shot prompt renderer for SAST (semgrep) findings."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from application.triage.prompts._fencing import (
    FENCING_PREAMBLE,
    POST_DATA_REMINDER,
    fence,
)

_LANG_MAP: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "php": "php",
    "rb": "ruby",
    "go": "go",
    "rs": "rust",
    "java": "java",
    "cs": "csharp",
    "c": "c",
    "cpp": "cpp",
    "h": "c",
    "hpp": "cpp",
    "sh": "bash",
    "bash": "bash",
    "yaml": "yaml",
    "yml": "yaml",
    "xml": "xml",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "json": "json",
}


def render(
    finding: dict[str, Any],
    *,
    file_contents: str,
    project: str,
) -> str:
    """Build a self-contained one-shot triage prompt."""
    finding_id = finding["id"]
    file_path = finding.get("file") or "unknown"

    sections: list[str] = [
        _PREAMBLE,
        FENCING_PREAMBLE,
        f"## Task\n\nTriage the following semgrep finding for project `{project}`.",
        "## Finding Record\n\n" + fence(_format_metadata(finding), "finding_metadata"),
        _build_source_section(file_path, file_contents),
        POST_DATA_REMINDER,
        _EPISTEMIC_CONSERVATISM,
        _output_schema(finding_id),
        _CONFIDENCE_GUIDANCE,
    ]
    return "\n\n".join(sections)


# -- private helpers --------------------------------------------------


def _format_metadata(finding: dict[str, Any]) -> str:
    fid = finding["id"]
    lines: list[str] = [
        f"- finding_id   : {fid}",
        f"- tool         : {_val(finding, 'tool')}",
        f"- rule_id      : {_val(finding, 'rule_id')}",
        f"- severity     : {_val(finding, 'severity')}",
        f"- file         : {_val(finding, 'file')}",
        f"- line_start   : {_val(finding, 'line_start')}",
        f"- cwe          : {_format_cwe(finding.get('cwe'))}",
        f"- description  : {_val(finding, 'description')}",
        f"- code_snippet : {_val(finding, 'code_snippet')}",
        f"- risk_type    : {_val(finding, 'risk_type')}",
        f"- owasp        : {_val(finding, 'owasp')}",
    ]
    return "\n".join(lines)


def _val(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if v is None:
        return "n/a"
    return str(v)


def _format_cwe(raw: Any) -> str:
    if raw is None:
        return "n/a"
    if isinstance(raw, list):
        return ", ".join(str(c) for c in raw) if raw else "n/a"
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw
        if isinstance(parsed, list):
            joined = ", ".join(str(c) for c in parsed)
            return joined if joined else "n/a"
        return str(parsed)
    return str(raw)


def _guess_lang(path: str) -> str:
    ext = PurePosixPath(path).suffix.lstrip(".")
    return _LANG_MAP.get(ext, ext or "text")


def _build_source_section(file_path: str, file_contents: str) -> str:
    if not file_contents:
        body = (
            f"Path: `{file_path}`\n\n"
            "The file could not be read. Set "
            "confidence=potential and note the reason "
            "in reasoning."
        )
        return "## Source File\n\n" + fence(body, "source_file")
    lang = _guess_lang(file_path)
    size = len(file_contents.encode("utf-8"))
    body = f"Path: `{file_path}` ({size} bytes)\n\n```{lang}\n{file_contents}\n```"
    return "## Source File\n\n" + fence(body, "source_file")


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
  evidence in the code path.
- Do NOT mark a finding `confirmed` unless you can trace user input
  to the sink through real, executing code (an AST data-flow match
  alone is NOT sufficient).
- When uncertain, prefer `potential` over `probable`, and `probable`
  over `confirmed`.
- If the source file could not be read, set confidence=potential and
  note the reason in `reasoning`.

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


def _output_schema(finding_id: int) -> str:
    return f"""\
## Output

Emit ONE strict JSON object on a single line. No code fences. No prose
before or after. No markdown. No leading whitespace. Schema:

{{"finding_id": {finding_id}, "confidence": "<confirmed|probable\
|potential|false_positive>", "finding_type": "<vulnerability|weakness\
|misconfiguration|exposure|dependency|informational|secret>", \
"severity": "<critical|high|medium|low|informational>", "reasoning": \
"<one paragraph addressing all four runtime-layer questions>", \
"remediation": "<one specific, actionable fix>", "attack_vector": \
"<HTTP method + path + parameter, or n/a>", "call_stack": \
["file:line function", ...]}}

Constraints:
- `finding_id` MUST equal {finding_id}.
- `call_stack` MUST be a (possibly empty) JSON array of strings.
- All string fields MUST be present. Use empty string only where
  genuinely not applicable.
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
