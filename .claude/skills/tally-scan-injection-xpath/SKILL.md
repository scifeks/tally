---
name: tally-scan-injection-xpath
description: >
  Scan the target repo for XPath injection defects. Detects string-formatted
  XPath queries, unparameterized XPath calls with user input, and template
  literals interpolating untrusted data into XPath expressions. Emits
  findings shaped for Tally MCP submission (rule_id `injection.xpath`,
  CWE-643, severity high). Invoke when the user says "XPath injection",
  "XPathi", "check for XPath injection", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: XPath injection

Detects sinks where user-controlled data reaches an XPath interpreter
without parameterization. Runs per-file in the target repo (as dispatched
by the `tally-scan-external` orchestrator, or standalone when the user
invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the `submit_finding`
MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.xpath` |
| Primary CWE | `CWE-643` |
| Secondary CWE | `CWE-74` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `XPathInjection` |


## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **String-formatted XPath (lxml)**: f-strings, .format(), or %-formatting
  that interpolate request-derived values into XPath expressions.
- **String-formatted XPath (ElementTree)**: string interpolation into the
  path argument of findall, find, or iterfind calls.
- **Concatenation into XPath**: building XPath expressions via string
  concatenation with request-derived values.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **DOMXPath query concatenation**: building query strings by interpolating
  request variables into XPath expressions.
- **SimpleXML xpath concatenation**: building xpath expressions with
  request-sourced values.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **xpath npm library concatenation**: building XPath expressions via string
  concatenation or template literals with request data.
- **xmldom evaluate concatenation**: building expressions for the evaluate
  method with request-derived values.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **xmldom (typed)**: same JavaScript patterns with type annotations.
- **xpath (typed npm)**: same JavaScript patterns with type annotations.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is XPath
  injection at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream variable
  that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to the
  sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly a
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not obviously
  user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.xpath`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
  attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-643", "CWE-74"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.xpath",
  "meta": {
    "title": "<short human title, e.g. 'XPath injection via f-string in
    user search'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
    traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Use the safe patterns from the per-language
reference files to write specific, actionable remediation.

- Name the library and its specific safe API
- Show the exact placeholder style or query builder method
- Keep it two to four sentences

## Common false positives

- **Static XPath expressions with no interpolation**: `tree.xpath(
  "//user[@active='1']")` is safe regardless of the library.
- **Constants and enums**: interpolation of module-level constants or enum
  values with no user reachability is safe. Confirm the value is not later
  reassigned from a request.
- **Validated input**: when the input is checked against an allowlist
  before reaching the sink, the pattern is safe. Confirm the validation
  matches the safe patterns shown in the language reference files.

## References

- `references/python.md`: Python patterns for lxml and xml.etree.ElementTree.
- `references/php.md`: PHP patterns for DOMXPath and SimpleXML.
- `references/javascript.md`: Node patterns for xpath npm and xmldom.
- `references/typescript.md`: TypeScript patterns for typed xpath and
  xmldom.
