# Canonical scanner-skill template

Every `tally-scan-<leaf>/SKILL.md` follows this shape. Slices 5-11
copy this template verbatim, filling in the per-skill values from
`docs/roadmap/TAL-148/taxonomy.md`. The payload every skill emits is
specified in `mcp-payload-shape.md`.

## Frontmatter template

```yaml
---
name: tally-scan-<leaf>
description: >
  <One paragraph that names the vulnerability class, lists the
  detection cues, and states that findings are emitted for Tally
  MCP submission. Include trigger phrases the user would type,
  e.g. "check for SQL injection", "scan for SQLi".>
---
```

The `name` field must match the directory name exactly. The
`description` field is what Claude Code reads to decide when to
activate the skill; be specific about the vulnerability class and
its detection cues.

## Skill authoring checklist

Every scanner SKILL.md must include:

- A frontmatter block with `name` and `description`.
- A `## Detection matrix` section grouped by language, one line per
  sink pattern.
- A `## Evidence requirements` section stating what every finding
  must include (file:line, code snippet, taint source when
  traceable).
- A `## Output payload skeleton` section with the fixed fields for
  this skill (rule_id, primary CWE, severity, meta.owasp_name),
  linking back to `mcp-payload-shape.md` for the full field list.
- A `## Common false positives` section listing patterns the
  scanner must NOT flag.
- A `## References` section linking to per-language reference
  files under `references/`.

Values to fill in from taxonomy T3 (skill row):

| Placeholder | Source |
|---|---|
| `<SKILL_ID>` | T3 column "skill_id" (dot-notation, e.g. `injection.sql`). Use verbatim in `rule_id`. |
| `<PRIMARY_CWE>` | T3 column "Primary CWE". Emit as `["CWE-N"]`. |
| `<SECONDARY_CWE>` | T3 column "Secondary CWE". Include in the `cwe` list after the primary when it adds signal. Omit otherwise. |
| `<OWASP_NAME>` | T3 column "OWASP 2025 category". Emit as `meta.owasp_name`. Use the NAME, not the numeric identifier. |
| `<PARENT_LABEL>` | T3 column "Parent label". Not emitted per finding; kept as authoring reference for cross-skill grouping. |
| `<DEFAULT_SEVERITY>` | T3 column "Default sev". Emit as `severity`. Adjust up or down per finding when the sink reaches production data or is dev-only. |

## Detection matrix template

Every language sub-section names the observable code patterns that
indicate the sink is reachable. Group by language: Python, PHP,
JavaScript, TypeScript.

```markdown
### Python

- <Sink pattern 1>: <how to recognize it>.
- <Sink pattern 2>: <how to recognize it>.
- <Sink pattern 3>: <how to recognize it>.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- <Sink pattern 1>: <how to recognize it>.

Defer to `references/php.md` for vulnerable-vs-safe snippets.
```

Adapt sink patterns to the vulnerability class. XSS sinks look
different from SQL-injection sinks; CSRF checks look different from
IDOR checks. The template is structural, not content.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink line.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  defect at this location.
- When the taint source is in the same file: `meta.taint_source`
  naming the request parameter or upstream variable that reaches
  the sink.

Do not emit a finding when:

- The sink pattern appears in a comment or docstring.
- The apparent source is a compile-time constant with no user
  reachability.
- The sink is guarded by an allowlist check that matches the safe
  patterns shown in the language reference file.

## Remediation instructions

Per D19, the scanner subagent writes `meta.remediation` inline for
every finding based on the actual library or framework observed in
the scanned code. There is no shared remediation table.

Guidance for the subagent:

- Name the library and the specific safe pattern. Examples:
  - `"Replace the f-string with a parameterized query. sqlite3 uses ? placeholders; call cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))."`
  - `"Use Prisma's typed where clause: prisma.user.findFirst({where: {username}}). Avoid $queryRaw when the shape is expressible through the query builder."`
  - `"Wrap the user input in escapeshellarg() before passing to exec(). Better, port this call to the pcntl_exec() interface which takes argv as an array and never invokes a shell."`
- Keep it two to four sentences. Long remediation prose does not
  render well in the report card.
- Reference the specific placeholder style, function name, or
  configuration key. Vague guidance ("use parameterization") is
  worse than no guidance because it reads as machine-generated.
- Do not include a full patch. The report is not a diff renderer;
  the developer opens the file and applies the guidance.

## Output payload skeleton

Every scanner SKILL.md ends with an example payload the subagent
copies and adapts per finding. Fill in the fixed fields; leave
the variable fields (`description`, `meta.title`,
`meta.remediation`, per-finding `line_number`, `code_snippet`) as
placeholders the subagent completes.

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose the report card renders>",
  "severity": "<DEFAULT_SEVERITY>",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["<PRIMARY_CWE>"],
  "finding_type": ["vulnerability"],
  "rule_id": "<SKILL_ID>",
  "meta": {
    "title": "<short human title>",
    "owasp_name": "<OWASP_NAME>",
    "remediation": "<per-finding remediation, per D19>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<request parameter or upstream variable, if traceable>"
  }
}
```

See `mcp-payload-shape.md` for the full field list, enum values,
and validator behavior.

## Constraints

- The subagent's final output is a JSON list of findings. Nothing
  else. The orchestrator parses the list and submits each finding
  individually.
- Never emit fields the validator does not accept
  (`mcp-payload-shape.md` "Required top-level fields" and
  "Optional top-level fields" are exhaustive at the top level;
  `meta.*` is open).
- Line length 88 characters for prose and code fences.
- Follow `~/.claude/claude-markdown/LANGUAGE.md`: no em dashes, no
  "utilize", "leverage", "ensure that", American English, no
  emoji, terse.

## Cross-skill dedup awareness

Per D24, findings across skills that share a family prefix (e.g.
`xss.stored`, `xss.reflected`, `xss.blind` all share `xss.`) will
be grouped as candidate duplicates when they land at the same file
and their line ranges overlap or fall within 10 lines of each
other. The LLM (running in the orchestrator's step 7) picks the
survivor.

When authoring a new skill in a family that already has siblings:

- Do not tune the skill to avoid emitting when a sibling would also
  emit. Over-emit and let dedup pick.
- Make the finding self-contained: another skill's finding may be
  the one that survives, so every finding must stand alone with a
  full description, remediation, and evidence.
