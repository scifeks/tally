---
name: tally-scan-access-control-incorrect-authz-logic
description: >
  Scan the target repo for incorrect authorization logic defects. Detects
  role and permission checks with wrong operators, overly broad role arrays,
  negated checks that over-permit, and type confusion in authorization
  comparisons. Emits findings shaped for Tally MCP submission
  (rule_id `access_control.incorrect_authz_logic`, CWE-863, severity high).
  Invoke when the user says "wrong authorization", "auth logic bug",
  "incorrect permission check", or when dispatched by `tally-scan-external`.
---

# Tally scanner: Incorrect authorization logic

Detects authorization checks where the boolean logic, permission scoping, or
type comparison allows unintended access. Runs per-file in the target repo
(as dispatched by the `tally-scan-external` orchestrator, or standalone when
the user invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the `submit_finding`
MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `access_control.incorrect_authz_logic` |
| Primary CWE | `CWE-863` |
| Secondary CWE | `CWE-284` |
| OWASP 2025 category | `Broken Access Control` |
| Default severity | `high` |
| Parent label (dedup) | `AuthzBypass` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row for incorrect authz.

## Detection matrix

### Python

- **OR logic in role check**: `if user.role == 'admin' or user.role ==
  'user'` guarding an admin-only path. Safe form uses `and` when multiple
  conditions must all hold, or a role set.
- **Always-true permission check**: `if has_perm('edit') or True` or any
  short-circuit that admits all users.
- **Negated check that over-permits**: `if user.role != 'guest'` admitting
  all non-guest roles when only 'admin' should access.
- **Overly broad decorator**: `@permission_required('view')` when the
  operation requires 'delete'. Safe form uses the correct permission name.
- **Wrong field in ownership check**: `if obj.id == request.user.id` instead
  of comparing `obj.owner_id` to `request.user.id`.
- **String case mismatch in comparison**: `role.lower() == 'admin'` when
  roles are stored mixed-case and comparison should be case-preserving.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Overly broad role array**: `in_array($user->role, ['admin', 'editor',
  'user'])` for admin-only action. Safe form limits to necessary roles.
- **Wrong gate definition**: `Gate::allows('update', $model)` with a gate
  that checks the wrong condition (e.g., checks read access instead of
  update).
- **Negated check that over-permits**: `if ($user->role !== 'guest')` when
  only 'admin' should access.
- **Wrong permission in policy**: `$this->authorize('view')` when the
  operation is 'delete'. Safe form uses the correct action.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Overly broad roles array**: `roles.includes(req.user.role)` with array
  `['user', 'admin']` for admin-only function.
- **Negated check that over-permits**: `if (user.role !== 'guest')`
  admitting all non-guest roles to an admin function.
- **Loose equality in role check**: `if (user.role == 1)` when role values
  are strings, or vice versa. Safe form uses strict equality.
- **JWT role not verified**: token payload checked without signature
  verification upstream.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Overly broad role decorator**: `@Roles('user', 'admin')` when only
  'admin' should access. Safe form lists only necessary roles.
- **Guard with incorrect boolean logic**: `canActivate` guard that returns
  `true` when the condition fails, or `false` when it succeeds.
- **Type-unsafe comparison**: role compared as number `user.roleId == 1`
  when roles are enums or strings.
- **CASL ability definition with overly permissive rule**: `can('read',
  'Article')` when the rule should be scoped per user or project.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the authorization check.
- `meta.code_snippet`: 2-6 lines of source containing the check.
- `meta.reasoning`: one sentence explaining why the check is incorrect.
- When the protected operation is evident from context:
  `meta.protected_operation` naming the action (e.g., 'delete', 'admin
  dashboard').

Set `confidence`:

- `confirmed` when the code path is clear and the operator/scope is
  demonstrably wrong.
- `probable` when the check pattern matches and the logic is suspicious,
  but the intended role set is inferred from surrounding code.
- `potential` when the check looks like authorization logic but the
  vulnerability is not obvious without tracing execution flow.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`access_control.incorrect_authz_logic`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the check, what access it allows, and
    what an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-863", "CWE-284"],
  "finding_type": ["vulnerability"],
  "rule_id": "access_control.incorrect_authz_logic",
  "meta": {
    "title": "<short human title, e.g. 'Negated role check admits all
      non-guests'>",
    "owasp_name": "Broken Access Control",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the check>",
    "protected_operation": "<action being gated, when clear>",
    "reasoning": "<one sentence explaining why the logic is incorrect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the framework and the
actual defect observed. Examples of good remediation strings:

- **Django `@permission_required`**: `Use the correct permission name for
  the operation. If deleting requires 'delete_article', decorate with
  @permission_required('delete_article'), not 'view_article'.`
- **PHP roles array**: `Change the allowed roles array from ['admin',
  'editor', 'user'] to ['admin'] so that only administrators can access
  this action.`
- **Negated role check**: `Use a positive assertion: `if (user.role ==
  'admin')` instead of `if (user.role !== 'guest')`. Negated checks are
  prone to logic errors when new roles are added.`
- **Loose equality in Node.js**: `Use strict equality (===) for role
  comparison: `if (user.roleId === ROLE_ADMIN)` instead of `==`. The loose
  comparison allows type confusion attacks.`
- **Overly broad CASL rule**: `Scope the permission to the current user or
  project: `can('update', 'Article', { author_id: user.id })` instead of
  `can('update', 'Article')`.`

Keep it two to four sentences. Vague guidance ("fix the authorization
check") is worse than no guidance.

## Common false positives

- **Defense-in-depth layered checks**: multiple guards, each correct for
  its scope. A positive assertion at the first guard is not a false
  positive even if later guards add additional checks.
- **Feature flags**: toggles that control whether a feature is available.
  Not a security authorization check.
- **Framework-provided authorization**: ORM-level `policy` classes,
  middleware guards with correct scoping, and declarative permission
  checks (e.g., `@Authorize(Roles.Admin)`) that match the framework
  documentation.
- **Test/mock authorization**: mocked or stubbed authorization in test
  files. Do not flag test helpers.
- **Public endpoints**: checks that allow all authenticated users (not
  guests) to an endpoint where that is the intended design. The pattern
  alone is not a defect if the endpoint is truly public.

## References

- `references/python.md`: Python patterns for Django permissions, DRF
  custom permission classes, manual role checks.
- `references/php.md`: PHP patterns for Laravel gates and policies, manual
  role checks, Spatie permissions.
- `references/javascript.md`: Node patterns for Express middleware role
  checks, manual comparisons.
- `references/typescript.md`: TypeScript patterns for NestJS guards, CASL,
  type-safe role enums.
