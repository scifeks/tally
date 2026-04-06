# Tools

## Supported Tools

| Tool | Category | What it does |
|---|---|---|
| OWASP ZAP | DAST | Dynamic web/API security scanning |
| OWASP Noir | Pre-DAST | Static endpoint discovery; produces an OAS3 spec for ZAP |
| Semgrep | SAST | Static analysis across many languages |
| tree-sitter | SAST | AST-based code analysis (Python library) |
| Gitleaks | Secrets | Git history and working-tree secret scanning |
| osv-scanner | SCA | Dependency vulnerability scanning via OSV database |
| pip-audit | SCA | Python dependency audit (PyPI advisory database) |
| npm-audit | SCA | Node.js dependency audit |
| composer-audit | SCA | PHP Composer dependency audit |

All tools are optional — Tally skips any tool that is not detected.

### pip-audit Dependency File

pip-audit behavior depends on the `dependencies_file` field in the repository configuration and the execution mode:

**Local mode** — `dependencies_file` is **required**. If the field is empty, pip-audit is skipped entirely for that repository. When set, pip-audit runs with `-r <dependencies_file>` to scan only declared dependencies. The path should be relative to the repo root (e.g. `requirements.txt`) or an absolute path on the host filesystem.

**Docker mode** — `dependencies_file` is **optional**. When empty, pip-audit scans all packages installed in the container environment (no `-r` flag). When set, the scan is scoped to declared dependencies via `-r <dependencies_file>`. The path should be the container-internal path (e.g. `/app/requirements.txt`).

Accepted file formats include `requirements.txt`, `Pipfile`, and any file format supported by `pip-audit -r`.

Set the dependencies file when adding a repository (`repo add` — Tally prompts automatically for Python repos) or update it later with `repo edit <name>`. You can also set it directly in `repositories.json`.

### OWASP Noir and ZAP

Noir is a static endpoint-discovery tool that analyses source code and emits an
OAS3 (OpenAPI 3) spec. Tally runs Noir before ZAP so that ZAP can use the
spec via `-openapifile` instead of relying on spider-only discovery. When no
Noir output exists for a repository, ZAP falls back to quickscan mode and may
miss API-only endpoints.

#### Node.js limitation

Noir's JavaScript parser has a known defect that causes it to enter an
effectively infinite loop on complex Node.js codebases. When this happens,
Noir exits without writing any output and makes no AI inference calls.

To avoid wasting scan time, Tally lets you mark a repository as a Node.js
app during `repo add` / `repo edit`. When JavaScript or TypeScript is
detected in the repository, Tally asks:

```
  Is this a Node.js app? (Noir will be skipped) [y/N]:
```

Answering `y` sets `node_app: true` in `repositories.json`. Noir is then
skipped for that repository across all scan types — full scans, targeted
tool scans, and when ZAP requests a Noir pre-scan. ZAP falls back to
quickscan mode for Node.js repositories.

This flag can be set or cleared at any time with `repo edit <name>`.

#### Endpoint file support

You can configure a path to an existing endpoint definition file (OAS3,
OAS2/Swagger, Postman collection, or HAR) on a repository using `repo add`
or `repo edit`. When set, Tally converts the file to OAS3 and passes it to
ZAP in place of a Noir-generated spec, bypassing Noir entirely. This works
for Node.js apps and for any project that already maintains an API spec.

See [docs/endpoint-files.md](endpoint-files.md) for supported formats,
setup instructions, and a description of how conversion works.

---

## Tool Detection

Tally calls `check_system_tools()` on startup and when you run the `tools` REPL command.
Three detection strategies are used:

1. **PATH lookup** (`shutil.which`) — used by most tools (semgrep, gitleaks, osv-scanner,
   pip-audit, npm-audit, composer-audit). A tool is available if its binary is on `$PATH`.
2. **Configured path** (`Path.exists`) — used by OWASP ZAP. Checks the absolute path set in
   `config/commands.json` (e.g. `/usr/share/zaproxy/zap.sh`), which allows ZAP to be detected
   even when not on `$PATH`.
3. **Python import** (`importlib.util.find_spec`) — used by tree-sitter. Checks that
   `tree_sitter` and `tree_sitter_language_pack` are importable in the active environment.
