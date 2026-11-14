# Domain family map

Maps vulnerability domain families to their component `tally-scan-*`
skills so the orchestrator dispatches one domain agent per family per
partition.

## Family table

| Family | Skill Directories | Primary Languages |
|---|---|---|
| injection | tally-scan-injection-sql, tally-scan-injection-template, tally-scan-injection-os-command, tally-scan-injection-ldap, tally-scan-injection-xpath, tally-scan-injection-nosql, tally-scan-injection-eval, tally-scan-injection-header, tally-scan-injection-reflection | Python, PHP, JavaScript, TypeScript |
| xss | tally-scan-xss-stored, tally-scan-xss-reflected, tally-scan-xss-blind | Python, PHP, JavaScript, TypeScript |
| access-control | tally-scan-access-control-csrf, tally-scan-access-control-idor-bola, tally-scan-access-control-incorrect-authz-logic, tally-scan-access-control-mass-assignment, tally-scan-access-control-missing-function-authz, tally-scan-access-control-open-redirect, tally-scan-access-control-path-traversal | Python, PHP, JavaScript, TypeScript |
| authentication | tally-scan-authentication-session-management, tally-scan-authentication-weak-or-missing-authn | Python, PHP, JavaScript, TypeScript |
| crypto | tally-scan-crypto-hardcoded-secrets, tally-scan-crypto-pii-in-logs, tally-scan-crypto-pii-in-response, tally-scan-crypto-weak-algorithm, tally-scan-crypto-weak-password-hashing, tally-scan-crypto-weak-prng | Python, PHP, JavaScript, TypeScript |
| data-integrity | tally-scan-data-integrity-file-upload, tally-scan-data-integrity-insecure-deserialization, tally-scan-data-integrity-missing-integrity-verification | Python, PHP, JavaScript, TypeScript |
| design-logic | tally-scan-design-logic-insufficient-logging, tally-scan-design-logic-missing-exception-handling, tally-scan-design-logic-order-of-operations, tally-scan-design-logic-race-condition, tally-scan-design-logic-toctou | Python, PHP, JavaScript, TypeScript |
| misconfig | tally-scan-misconfig-cors, tally-scan-misconfig-csp, tally-scan-misconfig-error-message-exposure, tally-scan-misconfig-framework-defaults, tally-scan-misconfig-insecure-file-permissions, tally-scan-misconfig-security-headers | Python, PHP, JavaScript, TypeScript |
| jwt | tally-scan-misconfig-jwt-alg-confusion, tally-scan-misconfig-jwt-jwks-injection, tally-scan-misconfig-jwt-missing-sig-verify | Python, PHP, JavaScript, TypeScript |
| network | tally-scan-ssrf, tally-scan-xxe | Python, PHP, JavaScript, TypeScript |

## Dispatch rules

- The orchestrator dispatches one domain agent per family per partition.
- A family is skipped for a partition when the partition contains NONE of
  the family's primary languages (based on file extensions in the
  partition's file list from the recon manifest).
- The JWT family is additionally skipped when the partition's files
  contain no JWT-related imports (grep for `jwt`, `jsonwebtoken`,
  `PyJWT`, `jose`, `firebase/php-jwt`).
- Each domain agent reads ALL SKILL.md files listed in its family's
  "Skill Directories" column. The agent uses these as reference material
  for detection patterns.
- Each domain agent also reads the relevant per-language reference files
  from each skill's `references/` subdirectory (e.g.,
  `references/python.md`, `references/php.md`) based on which languages
  are present in its partition.

## Skill path resolution

All skill directories are relative to `.claude/skills/`. The SKILL.md
within each directory is the detection reference. Per-language references
live at `<skill-dir>/references/<language>.md`.
