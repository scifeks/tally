---
name: tally-scan-injection-reflection
description: >
  Scan the target repo for unsafe reflection defects. Detects dynamic
  class/function/method instantiation and invocation on user-controlled
  values, method dispatch via getattr on request data, dynamic module
  loading from user input, and ReflectionClass instantiation from
  untrusted sources. Emits findings shaped for Tally MCP submission
  (rule_id `injection.reflection`, CWE-470, severity high). Invoke when
  the user says "unsafe reflection", "dynamic instantiation", "check for
  reflection attacks", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Unsafe reflection

Detects sinks where user-controlled data reaches reflection or dynamic
invocation mechanisms without validation. Runs per-file in the target
repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list
of findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.reflection` |
| Primary CWE | `CWE-470` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `UnsafeReflection` |


## Detection matrix

### Python

Read `references/python.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Method dispatch via reflection**: getattr calls with request-sourced
  attribute names, or dynamic lookup in globals or locals.
- **Dynamic module loading**: __import__ or importlib calls with
  request-derived module names.
- **Code execution**: exec or eval with any request-derived input.

### PHP

Read `references/php.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Variable class instantiation**: new with a request-sourced class name.
- **Variable function calls**: function names from request data passed to
  call_user_func or invoked via property access.
- **Reflection API**: ReflectionClass instantiation with untrusted class
  names.

### JavaScript

Read `references/javascript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Dynamic property access and invocation**: property names from request
  data used with bracket notation.
- **Dynamic code loading**: require or import calls with request-derived
  module identifiers.
- **Global or window property access**: property names from request data
  used to access module-level or global objects.

### TypeScript

Read `references/typescript.md` for vulnerable-vs-safe snippets.

Detect these sink categories:

- **Same as JavaScript**: dynamic property access and code loading patterns
  are identical at runtime regardless of TypeScript types.
- **Type-unsafe casting**: explicit type bypasses like casting to any do not
  prevent runtime vulnerabilities.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is unsafe
  at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler
  to the sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is
  clearly a variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not
  obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.reflection`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
  attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-470"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.reflection",
  "meta": {
    "title": "<short human title, e.g. 'Dynamic method dispatch on
    user input'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
    traceable>",
    "reasoning": "<one sentence explaining the defect at this
    location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library
observed in the code. Use the safe patterns from the per-language
reference files to write specific, actionable remediation.

- Name the library and its specific safe API
- Show the exact placeholder style or query builder method
- Keep it two to four sentences

## Common false positives

- **Static-key property access**: `obj.method()` or `obj['method']()`
  where the key is a string literal, not a variable. No user input.
- **Validated property access**: `obj[userInput]()` where `userInput`
  is checked against an explicit allowlist before use.
- **Dispatch tables**: `ALLOWED_METHODS[userInput]()` where
  `ALLOWED_METHODS` is a constant or frozen mapping and the user input
  can only select from its keys.
- **Type-safe reflective access**: `getattr(obj, attr)` where `attr`
  is from a typed Enum or fixed configuration constant with no user
  reachability.
- **Private/internal methods**: Reflection on methods that are
  genuinely private and never exposed to an attacker (e.g., internal
  framework helpers). If the method is internal but the name is still
  user-controlled, it is not safe.

## References

- `references/python.md`: Python patterns for getattr, importlib,
  `__import__`, globals/locals, exec/eval.
- `references/php.md`: PHP patterns for variable class instantiation,
  call_user_func, ReflectionClass.
- `references/javascript.md`: Node patterns for dynamic property
  access, require, import().
- `references/typescript.md`: TypeScript patterns for dynamic property
  access, require, import(), type-unsafe casting.
