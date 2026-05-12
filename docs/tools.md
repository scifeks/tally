# Tools

## Supported Tools

| Tool | Category | What it does |
|---|---|---|
| OWASP ZAP | DAST | Dynamic web/API security scanning |
| XSStrike | DAST | XSS-focused dynamic scanner; context-aware payload generation and WAF evasion to complement ZAP |
| OWASP Noir | Pre-DAST | Static endpoint discovery; produces an OAS3 spec for ZAP |
| Semgrep | SAST | Static analysis across many languages |
| tree-sitter | SAST | AST-based code analysis (Python library) |
| Gitleaks | Secrets | Git history and working-tree secret scanning |
| osv-scanner | SCA | Dependency vulnerability scanning via OSV database |
| pip-audit | SCA | Python dependency audit (PyPI advisory database) |
| npm-audit | SCA | Node.js dependency audit |
| composer-audit | SCA | PHP Composer dependency audit |
| Garak | LLM Security | LLM vulnerability scanning for prompt injection, jailbreaks, data leakage, and toxicity |

All tools are optional. Tally skips any tool that is not detected.

### pip-audit Dependency File

pip-audit behavior depends on the `dependencies_file` field in the repository configuration and the execution mode:

**Local mode.** `dependencies_file` is **required**. If the field is empty, pip-audit is skipped entirely for that repository. When set, pip-audit runs with `-r <dependencies_file>` to scan only declared dependencies. The path should be relative to the repo root (e.g. `requirements.txt`) or an absolute path on the host filesystem.

**Docker mode.** `dependencies_file` is **optional**. When empty, pip-audit scans all packages installed in the container environment (no `-r` flag). When set, the scan is scoped to declared dependencies via `-r <dependencies_file>`. The path should be the container-internal path (e.g. `/app/requirements.txt`).

Accepted file formats include `requirements.txt`, `Pipfile`, and any file format supported by `pip-audit -r`.

Set the dependencies file when adding a repository (`repo add`; Tally prompts automatically for Python repos) or update it later with `repo edit <name>`. You can also set it directly in `repositories.json`.

### OWASP Noir and ZAP

Noir is a static endpoint-discovery tool that analyzes source code and emits an OAS3 (OpenAPI 3) spec. Tally runs Noir before ZAP so ZAP can use the spec via `-openapifile` instead of relying on spider-only discovery. When no Noir output exists for a repository, ZAP falls back to quickscan mode and may miss API-only endpoints.

#### Node.js limitation

Noir's JavaScript parser has a known defect that causes it to enter an
effectively infinite loop on complex Node.js codebases. When this happens,
Noir exits without writing any output and makes no AI inference calls.

To avoid wasting scan time, Tally automatically detects Node.js repositories
by the presence of `package.json` at the repo root and skips Noir for them
across all scan types: full scans, targeted tool scans, and when ZAP
requests a Noir pre-scan. ZAP falls back to quickscan mode for Node.js
repositories.

#### Endpoint file support

You can configure a path to an existing endpoint definition file (OAS3,
OAS2/Swagger, Postman collection, or HAR) on a repository using `repo add`
or `repo edit`. When set, Tally converts the file to OAS3 and passes it to
ZAP in place of a Noir-generated spec, bypassing Noir entirely. This works
for Node.js apps and for any project that already maintains an API spec.

See [docs/endpoint-files.md](endpoint-files.md) for supported formats,
setup instructions, and a description of how conversion works.

---

## XSStrike

XSStrike is an XSS-focused DAST tool that uses context-aware payload generation and WAF evasion techniques to detect cross-site scripting vulnerabilities. It runs alongside OWASP ZAP in the `web` scan segment, targeting XSS that ZAP may miss due to its generic payload set.

### Requirements

- **XSStrike binary.** Clone from `https://github.com/s0md3v/XSStrike` and make the entry point available on `$PATH` as `xsstrike`, or configure the full path in `config/commands.json`.
- **FuzzyWuzzy.** Installed automatically with Tally (`fuzzywuzzy` and `python-Levenshtein`). XSStrike uses it for response similarity analysis. Without it, the tool still runs but with reduced detection accuracy. For Docker installs, both packages are installed in the container.

### URL seed mode

XSStrike requires a running web application with a configured `base_url`.
When adding or editing a repository that has base URLs set, Tally prompts for
the URL seed mode:

| Mode | Description | Default when |
|------|-------------|--------------|
| `provided` | Generate seeds from the user-supplied endpoint file (`oas3_path` → URL list) | `oas3_path` is set |
| `noir` | Generate seeds from the most recent Noir OAS3 output for the repository | No endpoint file |
| `crawl` | XSStrike spiders from `base_url` directly | Fallback / third option |

Priority logic:
1. If the repository has a user-supplied endpoint file (`oas3_path`), the wizard
   defaults to `provided`.
2. If no endpoint file is set, the wizard defaults to `noir` (seeds are
   generated from Noir's endpoint discovery output at scan time).
3. `crawl` is always available as an explicit option.

When `noir` mode is selected but no Noir output exists for the repository at scan time, XSStrike falls back to `crawl` mode automatically. The same fallback applies to `provided` mode when `oas3_path` is empty.

Set or change the mode at any time with `repo edit <name>`.

---

## Garak LLM Scanner

Garak requires a YAML configuration file specifying the target LLM (model type, model name, probes to run). The config is per-repository since different repos may target different LLMs.

You can provide the config file in two ways:

- **REPL.** During `repo add` or `repo edit`, Tally prompts for a local file path and copies it to the project's config directory.
- **Web UI.** On the Config page, select a repository and upload a `.yaml` or `.yml` file in the LLM Scanning section.

When no garak config file is present for a repository, the tool is skipped automatically for that repo.

### Timeout

Garak defaults to a 3600-second (1 hour) timeout. For large probe sets or slow models, set a custom timeout in the config file under a `tally` section:

```yaml
tally:
  timeout: 7200

plugins:
  target_type: ollama
  # ...
```

The `tally` section is ignored by garak itself and only read by Tally.

See the [garak documentation](https://github.com/NVIDIA/garak) for config file format and available probes.

---

## Tool Detection

Tally calls `check_system_tools()` on startup and when you run the `tools` REPL command.
Three detection strategies are used:

1. **PATH lookup** (`shutil.which`). Used by most tools (semgrep, gitleaks, osv-scanner, pip-audit, npm-audit, composer-audit). A tool is available if its binary is on `$PATH`.
2. **Configured path** (`Path.exists`). Used by OWASP ZAP. Checks the absolute path set in `config/commands.json` (e.g. `/usr/share/zaproxy/zap.sh`), which allows ZAP to be detected even when not on `$PATH`.
3. **Python import** (`importlib.util.find_spec`). Used by tree-sitter. Checks that `tree_sitter` and `tree_sitter_language_pack` are importable in the active environment.
