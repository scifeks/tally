---
name: tally-scan-adversarial
description: >
  Verify a batch of pre-submission security findings using a
  courtroom-style adversarial pattern. For each finding,
  dispatches prosecutor, defense, and expert-witness
  deep-investigator agents in parallel, then adjudicates to
  produce a verified subset and a dropped-with-reason list.
  Invoke when dispatched by tally-scan-external or when the user
  says "adversarial verification", "verify these findings", or
  "run adversarial pass".
---

# Adversarial finding verification

Verify pre-submission security findings before they reach Tally.
For each finding, dispatch three deep-investigator agents in
parallel using a courtroom-style adversarial pattern. The
prosecutor builds the case that the vulnerability is real, the
defense argues it is a false positive, and an expert witness
gathers objective evidence. The orchestrating agent acts as
judge, reads the code, and weighs both sides to produce a
filtered batch.

The adversarial structure matters: the tension between
prosecution and defense filters out false positives that a
single-pass review would miss, while the expert witness provides
the factual foundation that prevents either side from
fabricating evidence.

## Input

A JSON list of finding dicts. Each dict follows the shape in
`.claude/skills/tally-scan-external/references/mcp-payload-shape.md`.
Required fields per finding: `file`, `line_number`,
`description`, `rule_id`, `cwe`, `meta` (with `title`,
`owasp_name`, `remediation`).

## Output

```json
{
  "verified": [
    <finding dicts that survived adjudication, unchanged>
  ],
  "dropped": [
    {
      "finding": <original finding dict>,
      "reason": "<one-sentence reason for dropping>"
    }
  ]
}
```

## Steps

### Step 1: Parse the finding batch

Read the input batch. Count the findings. For each finding,
confirm it has `file`, `line_number`, `description`, `rule_id`,
and `cwe`. If a finding is missing required fields, drop it with
reason "Missing required fields: <list>".

Report: "Verifying N findings."

### Step 2: Verify each finding

For each finding in the batch, dispatch three
`deep-investigator` subagents in a single message using the
Agent tool so they run concurrently.

All three agents MUST use
`subagent_type: "deep-investigator"`. Do not use Explore,
general-purpose, or any other agent type.

Fill in the finding's fields into each role's prompt template
from the references directory. Replace every `<field>` placeholder
with the finding's actual value.

**Agent 1: Prosecutor (Vulnerability Prosecutor)**

Use the prompt template from `references/prosecutor.md`. The
prosecutor traces the code at the cited location to build the
case that the vulnerability is real and exploitable.

**Agent 2: Defense (False Positive Advocate)**

Use the prompt template from `references/defense.md`. The
defense searches for framework protections, safe patterns,
input sanitization, or misidentification that would make this
finding a false positive.

**Agent 3: Expert Witness (Evidence Gatherer)**

Use the prompt template from `references/expert-witness.md`.
The expert witness gathers objective evidence about the library,
framework, and input handling chain without taking a position.

Wait for all three agents to return before proceeding to
adjudication for this finding.

### Step 3: Adjudicate (you are the Judge)

When all three agents return for a finding, you act as the
judge. Weigh the prosecution's case against the defense's
arguments, using the expert witness's evidence as the factual
foundation.

**Before rendering a verdict, read the code at the cited
file:line yourself.** Do not take either agent's claims at face
value.

Apply this rubric:

1. **Verified (prosecution prevails).** The prosecutor
   demonstrated a taint trace from untrusted input to the sink.
   The defense could not identify a concrete guard (sanitizer,
   parameterization, type coercion, allowlist) in the path. The
   expert witness's evidence is consistent with the vulnerability.
   Add the finding to `verified` unchanged.

2. **Dropped (defense prevails).** The defense identified a
   specific protection mechanism (name the function, middleware,
   or framework feature) that prevents exploitation, and the
   expert witness confirmed the guard exists. Or the defense
   showed the sink is unreachable from untrusted input. Or the
   defense demonstrated the scanner misread the code pattern.
   Add the finding to `dropped` with a one-sentence reason
   naming the specific guard or misidentification.

3. **Tie goes to prosecution.** If both sides present plausible
   arguments and the expert witness's evidence does not clearly
   favor either, keep the finding. A false negative (dropping a
   real vulnerability) is worse than a false positive (keeping a
   finding that manual review catches later). Add to `verified`.

Record the verdict and rationale, then proceed to the next
finding.

### Step 4: Return results

After all findings are adjudicated, return:

```json
{
  "verified": [<surviving finding dicts, unchanged>],
  "dropped": [
    {"finding": <original dict>, "reason": "..."}
  ]
}
```

Report to the caller: total findings received, verified count,
dropped count.

## Adjudication examples

**Verified.** Prosecutor traced `request.args.get('id')` through
an f-string into `cursor.execute()` at `app/views.py:42`.
Defense found no parameterization or input validation in the
path. Expert confirmed Flask does not auto-sanitize query
parameters.

**Dropped.** Defense showed the finding flagged
`db.session.execute(text(query), {"id": user_id})` which uses
SQLAlchemy bound-parameter syntax. Expert confirmed `text()`
with dict bindings auto-parameterizes. Reason: "Uses SQLAlchemy
bound-parameter syntax; query is parameterized."

**Dropped.** Defense showed the flagged function is called only
from `management/commands/seed_db.py`, a Django management
command that takes no external input. Expert confirmed no route
or view calls this function. Reason: "Sink unreachable from
untrusted input; called only from internal management command."

**Verified (tie).** Prosecutor identified string interpolation
into a raw SQL query. Defense argued the value comes from an
internal config file. Expert could not confirm whether the
config file is user-editable. Kept: taint source ambiguous, sink
pattern unsafe regardless of source.

## Constraints

- All three agents MUST use
  `subagent_type: "deep-investigator"`.
- Do not modify finding payloads. Verified findings pass through
  unchanged. Dropped findings are wrapped with the original dict
  plus a reason string.
- When in doubt, keep the finding. False negatives cost more
  than false positives in security scanning.
- Do not evaluate formatting or field completeness. The MCP
  validator handles that downstream. Focus on whether the
  vulnerability is real.
- Process findings sequentially: dispatch 3 agents for one
  finding, adjudicate, then move to the next. This keeps the
  judge's context focused per finding.

## References

- `references/prosecutor.md`: prompt template for the
  vulnerability prosecutor role
- `references/defense.md`: prompt template for the false
  positive advocate role
- `references/expert-witness.md`: prompt template for the
  evidence gatherer role
