"""One-shot prompt renderer for dependency/SCA findings."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from application.triage.prompts._fencing import (
    FENCING_PREAMBLE,
    POST_DATA_REMINDER,
    fence,
)


def render(
    finding: dict[str, Any],
    *,
    file_contents: str,
    project: str,
) -> str:
    """Build a self-contained one-shot triage prompt."""
    finding_id = finding["id"]
    file_path = finding.get("lockfile") or "unknown"

    sections: list[str] = [
        _PREAMBLE,
        FENCING_PREAMBLE,
        (
            "## Task\n\n"
            "Triage the following dependency/SCA finding "
            f"for project `{project}`."
        ),
        _SCA_CONTEXT_NOTE,
        (
            "## Finding Record\n\n"
            + fence(_format_metadata(finding), "finding_metadata")
        ),
        _build_lockfile_section(file_path, file_contents),
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
        f"- finding_id       : {fid}",
        f"- tool             : {_val(finding, 'tool')}",
        f"- package_name     : {_val(finding, 'package_name')}",
        f"- package_version  : {_val(finding, 'package_version')}",
        f"- ecosystem        : {_val(finding, 'ecosystem')}",
        f"- vulnerability_id : {_val(finding, 'vulnerability_id')}",
        f"- severity         : {_val(finding, 'severity')}",
        f"- cvss_score       : {_val(finding, 'cvss_score')}",
        f"- cvss_vector      : {_val(finding, 'cvss_vector')}",
        f"- fixed_version    : {_val(finding, 'fixed_version')}",
        f"- description      : {_val(finding, 'description')}",
        f"- aliases          : {_val(finding, 'aliases')}",
        f"- references       : {_val(finding, 'references')}",
        f"- cwe_ids          : {_format_cwe(finding.get('cwe_ids'))}",
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


_LANG_MAP: dict[str, str] = {
    "json": "json",
    "lock": "json",
    "txt": "text",
    "toml": "toml",
    "cfg": "ini",
    "ini": "ini",
    "yaml": "yaml",
    "yml": "yaml",
    "xml": "xml",
}


def _build_lockfile_section(file_path: str, file_contents: str) -> str:
    if not file_contents:
        body = (
            f"Path: `{file_path}`\n\n"
            "The lockfile could not be read. Set "
            "confidence=potential and note the reason "
            "in reasoning."
        )
        return "## Lockfile\n\n" + fence(body, "lockfile_content")
    lang = _guess_lang(file_path)
    size = len(file_contents.encode("utf-8"))
    body = f"Path: `{file_path}` ({size} bytes)\n\n```{lang}\n{file_contents}\n```"
    return "## Lockfile\n\n" + fence(body, "lockfile_content")


# -- static prompt text -----------------------------------------------

_PREAMBLE = """\
You are a web application security analyst performing automated triage.
This session is NON-INTERACTIVE. You must complete all work and exit.
Do NOT ask questions. Do NOT wait for input. Finish and exit."""

_SCA_CONTEXT_NOTE = """\
## SCA Context

The vulnerability exists in the dependency version itself. No code-path
tracing is required to confirm it exists. Your job is to assess
exploitability in context and provide actionable remediation."""

_EPISTEMIC_CONSERVATISM = """\
## Epistemic Conservatism

This is the most important section. Read it carefully before assigning
any confidence level.

- The vulnerability exists in the advisory database for this version.
  You are assessing exploitability, not discovering it.
- Is the package actively imported in production code, or is it
  dev-only / CLI tooling? If the lockfile is available, check whether
  the package appears and whether it is direct or transitive.
- A network-exploitable vulnerability in dev-only tooling has lower
  effective severity.
- Do not speculate about exploit chains beyond the advisory data.
- Do not inflate severity beyond what CVSS and context support.

For any finding, explicitly answer each question in your `reasoning`
field:

**1. Is the package actively imported in production paths?**
   Check the lockfile for the package entry. A package present only as
   a transitive dependency of a dev tool (linter, test framework) is
   lower risk. If the lockfile is not available, note this uncertainty.

**2. Does the CVSS vector match the deployment context?**
   A network-exploitable vulnerability (AV:N) in a package used only
   for local CLI tooling may warrant lower effective severity. A
   vulnerability requiring local access (AV:L) in a server-side
   package may still be relevant if the server is shared.

**3. Is a fix available?**
   Check the `fixed_version` field. If a patched version exists,
   remediation is straightforward. If no fix exists, note whether a
   replacement package or workaround is available.

**4. Is there a known public exploit?**
   Advisory databases sometimes note whether a public proof of concept
   exists. A CVE with a public PoC is higher urgency than one that is
   theoretical."""


def _output_schema(finding_id: int) -> str:
    return f"""\
## Output

Emit ONE strict JSON object on a single line. No code fences. No prose
before or after. No markdown. No leading whitespace. Schema:

{{"finding_id": {finding_id}, "confidence": "<confirmed|probable\
|potential|false_positive>", "finding_type": "<vulnerability|weakness\
|misconfiguration|exposure|dependency|informational|secret>", \
"severity": "<critical|high|medium|low|informational>", "reasoning": \
"<one paragraph addressing all four SCA-context questions>", \
"remediation": "<specific fix: upgrade to >= Y.Z, or replace with \
alternative>", "attack_vector": "<attack surface from CVSS, or n/a>", \
"call_stack": ["file:line function", ...]}}

Constraints:
- `finding_id` MUST equal {finding_id}.
- `call_stack` MUST be a (possibly empty) JSON array of strings.
  For dependency findings this is typically empty.
- All string fields MUST be present. Use empty string only where
  genuinely not applicable.
- Output the JSON, then stop. Do NOT continue producing text."""


_CONFIDENCE_GUIDANCE = """\
## Confidence Guidance

- confirmed: CVE confirmed for this exact version; package actively
  imported in production paths; exploit path is viable.
- probable: CVE confirmed but package appears dev-only or unused in
  production paths.
- potential: Version range ambiguity, or lockfile not available to
  confirm the package is actually pulled in.
- false_positive: Safe version despite advisory (e.g. distro
  backported fix), or package is not actually included."""
