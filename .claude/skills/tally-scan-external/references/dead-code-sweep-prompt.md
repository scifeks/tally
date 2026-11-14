# Dead code sweep: ${FAMILY_NAME}

## Mission

You scan unreachable code for dangerous patterns in the ${FAMILY_NAME}
vulnerability family. This code was identified by the recon phase as not
reachable from any production entry point. You use pattern-based detection
(not input-forward tracing, since dead code has no inputs to trace from).
Every finding defaults to `weakness` classification because the code is
not currently exploitable, but the patterns are inherently dangerous if
activated.

## Your dead code scope

Scan only the files listed in the dead code inventory below. Do not scan
files in any active partition's scope.

```
${DEAD_CODE_INVENTORY}
```

## Detection references

Read these skill files for detection patterns:

```
${SKILL_FILE_LIST}
```

Read these language reference files:

```
${LANGUAGE_REF_LIST}
```

## Scanning procedure

1. **Read each file in the dead code inventory.** For each file matching
   your family's relevant languages (by file extension), read the complete
   file contents.

2. **Pattern match against detection matrices.** For each sink pattern in
   your family's skill files, check whether the code contains that pattern.
   You are not tracing from a known input; you are looking for dangerous
   sinks regardless of input source. A dangerous pattern in dead code is
   still a dangerous pattern.

3. **Check for potential input paths.** Even though the code is unreachable
   from known entry points:
   a. Does the function accept parameters that could be user-controlled if
      called?
   b. Does the function read from a data store that could contain user
      data?
   c. Does the file define routes or handlers that are not wired into the
      application's routing?
   d. Could this function be called dynamically (via reflection, dynamic
      import, or property lookup)?
   If yes to any, note this in the finding's reasoning.

4. **Build the finding payload.** For each finding:
   - `confidence`: `potential` (mandatory for all dead code findings)
   - `finding_type`: `["weakness"]` (mandatory for all dead code findings)
   - `severity`: based on the pattern's inherent danger level from the
     skill's default severity. Do not downgrade severity just because the
     code is dead. A weakness can still be high severity.
   - `meta.reachability`: `unreachable`
   - `meta.dead_code_reason`: one of `no_caller`, `no_route`,
     `unused_import`, `disabled_feature`
   - All other fields per `mcp-payload-shape.md`

## What NOT to report in dead code

- Configuration files or static assets
- Comments containing dangerous patterns (example SQL in a docstring is
  not a finding)
- Generated code or vendored dependencies
- Test files (these are excluded from the dead code inventory by recon,
  but skip if encountered)
- Patterns where the sink is actually a safe variant (parameterized SQL
  queries, `subprocess.run` with a list argument, proper encoding on
  output)

## Output format

Return ONLY a JSON list of finding objects. Each finding must include all
required fields from `mcp-payload-shape.md`. If no findings, return `[]`.

```json
[
  {
    "file": "src/legacy/old_api.py",
    "line_number": 23,
    "description": "Unreachable function constructs SQL query via f-string. Not currently exploitable but dangerous if activated.",
    "severity": "high",
    "confidence": "potential",
    "cwe": ["CWE-89"],
    "finding_type": ["weakness"],
    "rule_id": "injection.sql",
    "reasoning": "Dead code: process_query() has no callers. Gate 1: unreachable. Gate 2: parameter would be attacker-controlled if called. Gate 3: no sanitization. Gate 4: would allow data exfiltration.",
    "meta": {
      "title": "SQL injection pattern in dead code",
      "owasp_name": "Injection",
      "remediation": "Replace the f-string with parameterized query using sqlite3 ? placeholders, or remove the file if abandoned.",
      "code_snippet": "def process_query(user_input):\n    query = f\"SELECT * FROM data WHERE name = '{user_input}'\"\n    cursor.execute(query)",
      "reachability": "unreachable",
      "dead_code_reason": "no_caller",
      "gate_results": {
        "reachability": "unreachable",
        "attacker_control": "potential_parameter",
        "sanitization": "none",
        "impact": "data_exfiltration"
      }
    }
  }
]
```

## Constraints

- Return the JSON list only, nothing else. No preamble, no explanation.
- Only scan files from the dead code inventory. Do not discover other
  files.
- Default all findings to `confidence: potential` and `finding_type:
  ["weakness"]`. This is mandatory.
- Do not set `confidence: confirmed` for dead code (the code is not
  exercised).
- Do not emit `finding_type: ["false_positive"]` (adversarial
  verification handles that).
- Remediation should suggest either fixing the pattern or removing the
  dead code.
- Follow LANGUAGE.md: no em dashes, American English, no emoji, terse.
