# Tools

## Supported Tools

| Tool | Category | What it does |
|---|---|---|
| Antares | SAST | CWE vulnerability localization using LLM agent investigation. Identifies files likely to contain specific CWE weaknesses by exploring the codebase with a small language model. Requires endpoint configuration; see [docs/antares-shim.md](antares-shim.md) |
| Nuclei | DAST | Template-based vulnerability scanner; known CVE fingerprinting, misconfiguration detection, and DAST fuzzing |
| OWASP ZAP | DAST | Dynamic web/API security scanning |
| XSStrike | DAST | XSS-focused dynamic scanner; context-aware payload generation and WAF evasion to complement ZAP |
| graphql-cop | DAST | GraphQL security auditing; tests for introspection, batching, alias abuse, field suggestions, and other misconfigurations |
| OWASP Noir | Pre-DAST | Static endpoint discovery; produces an OAS3 spec for ZAP |
| Psalm | SAST | PHP taint analysis; traces data flow from user input to dangerous sinks (SQL injection, XSS, command injection) |
| Semgrep | SAST | Static analysis across many languages |
| tree-sitter | SAST | AST-based code analysis (Python library) |
| Gitleaks | Secrets | Git history and working-tree secret scanning |
| osv-scanner | SCA | Dependency vulnerability scanning via OSV database |
| pip-audit | SCA | Python dependency audit (PyPI advisory database) |
| npm-audit | SCA | Node.js dependency audit |
| composer-audit | SCA | PHP Composer dependency audit |
| Retire.js | SCA | Vulnerable JavaScript library detector; scans JS files directly for known CVEs without requiring a lockfile |
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

## LLM Endpoint Extraction

LLM endpoint extraction is an alternative URL discovery mechanism that complements Noir and Katana. When configured, Tally uses an LLM to read controller source code and extract HTTP routes, query parameters, and form parameters, producing parameterized URLs for DAST tools.

### When it triggers

Endpoint extraction runs automatically during scans when both conditions are met:

1. Noir is skipped for the repository (unsupported framework) or returns zero endpoints
2. The `endpoint_extraction_inference` feature is configured in `config/global.json`

The scan also checks the URL inventory; if it contains endpoints, extraction is skipped to avoid redundant work.

### What it produces

Extracted endpoints become informational findings (same as Noir and Katana output) and feed downstream DAST tools (sqlmap, dalfox, xsstrike) that require parameterized URLs.

### Provider options

Choose a provider based on your needs:

- **Ollama or llama.cpp.** Run inference locally at no API cost. Fast, suitable for small-to-medium codebases. Set `base_url` in the `ollama` or `llama_cpp` provider config and reference it in `endpoint_extraction_inference`.
- **Claude API.** Higher accuracy on complex endpoint patterns and modern frameworks. Requires Anthropic API key. Set `api_key` in the `claude` provider config and reference it in `endpoint_extraction_inference`.

See [docs/configuration.md](configuration.md) for examples of enabling endpoint extraction with each provider.

---

## Psalm

Psalm is a PHP static analyzer whose taint analysis mode traces data flow from user-controlled sources (`$_GET`, framework request objects) to dangerous sinks (`DB::raw()`, `shell_exec`, `echo`) across function boundaries. Unlike pattern-matching SAST tools, Psalm follows data through assignments, function calls, and return values to detect injection vulnerabilities that require path-sensitive analysis.

### Setup

Psalm is optional and auto-detected via `$PATH`. Install globally or per-project via Composer:

```bash
composer require --dev vimeo/psalm
```

### Taint stubs

Tally ships PHP stub files that teach Psalm which framework methods are taint sources and sinks. Configure stubs per repository with `repo edit <name>`:

| Stub | Covers |
|---|---|
| `php_builtins` | PHP superglobals (`$_REQUEST`, `$_SERVER`, `$_FILES`), `shell_exec`, `eval`, PDO, `file_get_contents`, `header` |
| `slim` | PSR-7 `ServerRequestInterface` and Slim `Request::getParam()` |
| `eloquent` | `DB::raw()`, `whereRaw()`, `selectRaw()`, `orderByRaw()`, `havingRaw()`, `groupByRaw()` |
| `symfony_console` | `InputInterface::getArgument()`, `InputInterface::getOption()` |

`php_builtins` is always included regardless of configuration. The default is `["php_builtins"]`. To add framework stubs, set the `psalm_stubs` field on the repository:

```json
{
  "psalm_stubs": ["php_builtins", "slim", "eloquent"]
}
```

### How it works

The adapter generates a temporary `psalm.xml` per scan with taint analysis enabled, the configured stubs, and source directories extracted from `composer.json` or an existing `psalm.xml`. The target repository is never modified. Psalm outputs SARIF and the adapter filters to `Tainted*` findings only, ignoring code quality issues.

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

## Nuclei

Nuclei is a template-based vulnerability scanner that identifies specific known vulnerabilities (CVEs), misconfigurations, and exposures on live targets using YAML templates from a community-maintained library of 9000+ detection rules.

### Two-pass scanning

Nuclei runs in two passes per repository:

1. **Automatic scan** (`-as`): Uses Wappalyzer-style technology fingerprinting to detect what's running on the target, then selects templates matching the detected stack. Scans for critical, high, and medium severity findings.
2. **DAST fuzzing** (`-dast`): Runs fuzzing templates that actively probe for vulnerabilities. Scans for critical and high severity only to reduce noise.

Both passes consume all available URLs: base URLs, URLs discovered by Noir/Katana, and user-uploaded URL lists.

### Custom templates

Place a `.nuclei/` directory at the root of your repository to include organization-specific templates alongside the default library. Any YAML templates in this directory are automatically included in both scan passes.

### What Nuclei covers that other tools don't

- Known CVE fingerprinting against live targets (1496 known-exploited vulnerabilities)
- SSL/TLS vulnerability scanning
- Technology-specific misconfigurations and exposed admin panels
- Network protocol scanning (DNS, TCP, WebSocket)
- Default credential detection

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

## Retire.js

Retire.js detects known-vulnerable JavaScript libraries by scanning `.js` files directly. Unlike npm-audit, it does not require a `package.json` or lockfile, making it suitable for legacy projects, vendor directories, and applications that bundle third-party JavaScript without a package manager.

### Requirements

- **retire binary.** Install via npm: `npm install -g retire`. The binary must be on `$PATH` or configured in `config/commands.json`.

### How it works

Retire.js scans the repository directory for JavaScript files and matches their content against a database of known vulnerable library versions. Findings include the CVE ID, affected component name and version, severity, and the file path where the vulnerable library was found. The scanner uses the `--exitwith 0` flag for consistent exit handling and outputs JSON to stdout.

Retire.js is language-gated to JavaScript repositories. It runs only when the repository has a `javascript` language tag configured.

---

## Search Fields by Tool

The REPL `search` command filters findings by field values. Each tool exposes a different set of searchable fields depending on what information it produces.

Run `search --show-fields --tool=<tool>` to see all available fields for a tool. You can then filter by any field: `search --severity=high --tool=semgrep` or `search --file_path=src/auth.php --tool=psalm`.

### composer-audit

| Field | Description |
|---|---|
| `ecosystem` | Package ecosystem (Packagist) |
| `file_path` | Source file path (composer.json) |
| `finding_type` | Type of finding (dependency) |
| `package_name` | Name of the affected package |
| `severity` | Severity level (low, medium, high, critical) |
| `vulnerability_id` | CVE or advisory ID |

### dalfox

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed, probable, potential) |
| `cwe` | CWE ID of the XSS vulnerability |
| `evidence` | Evidence captured from the response |
| `finding_type` | Type of finding (vulnerability) |
| `inject_type` | Type of XSS injection |
| `message` | Additional message or note |
| `method` | HTTP method used in the payload |
| `param` | Parameter that is vulnerable |
| `payload` | XSS payload that triggered the finding |
| `poc` | Proof of concept URL |
| `severity` | Severity level (low, medium, high, critical) |
| `url` | URL where the vulnerability was found |

### garak

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed, probable, potential) |
| `domain` | Security domain (web) |
| `finding_type` | Type of finding (vulnerability) |
| `fingerprint` | Unique fingerprint for the probe and detector pair |
| `probe` | Name of the garak probe that failed |
| `severity` | Severity level (low, medium, high, critical) |
| `tool` | Tool name (garak) |

### gitleaks

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed) |
| `domain` | Security domain (code) |
| `file_path` | File path where the secret was found |
| `finding_type` | Type of finding (secret) |
| `severity` | Severity level (high) |
| `tool` | Tool name (gitleaks) |

### graphql-cop

| Field | Description |
|---|---|
| `description` | Description of the misconfiguration |
| `finding_type` | Type of finding (vulnerability) |
| `rule_id` | Slugified rule ID |
| `severity` | Severity level (low, medium, high, critical) |
| `url` | Target GraphQL endpoint URL |

### katana

| Field | Description |
|---|---|
| `description` | Endpoint description |
| `finding_type` | Type of finding (informational) |
| `method` | HTTP method (GET, POST, etc.) |
| `severity` | Severity level |
| `url` | Discovered endpoint URL |

### noir

| Field | Description |
|---|---|
| `description` | Endpoint description |
| `finding_type` | Type of finding (informational) |
| `method` | HTTP method (GET, POST, etc.) |
| `severity` | Severity level |
| `url` | Discovered endpoint path |

### npm-audit

| Field | Description |
|---|---|
| `ecosystem` | Package ecosystem (npm) |
| `file_path` | Source file path (package.json) |
| `finding_type` | Type of finding (dependency) |
| `package_name` | Name of the affected package |
| `severity` | Severity level (low, medium, high, critical) |
| `vulnerability_id` | CVE or advisory ID |

### nuclei

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed) |
| `finding_type` | Type of finding (vulnerability, misconfiguration, exposure) |
| `host` | Target host scanned |
| `matched_at` | URL where the template matched |
| `matcher_name` | Name of the matcher that triggered |
| `severity` | Severity level (low, medium, high, critical) |
| `tags` | Comma-separated template tags |
| `template_id` | Nuclei template ID |
| `type` | Type of Nuclei detection |
| `url` | Full URL where the finding was detected |
| `vulnerability_id` | CVE ID if applicable |

### osv-scanner

| Field | Description |
|---|---|
| `ecosystem` | Package ecosystem (PyPI, npm, etc.) |
| `file_path` | Source file path (requirements.txt, etc.) |
| `finding_type` | Type of finding (dependency) |
| `package_name` | Name of the affected package |
| `severity` | Severity level (low, medium, high, critical) |
| `vulnerability_id` | OSV vulnerability ID |

### pip-audit

| Field | Description |
|---|---|
| `ecosystem` | Package ecosystem (PyPI) |
| `file_path` | Source file path |
| `finding_type` | Type of finding (dependency) |
| `package_name` | Name of the affected package |
| `severity` | Severity level (low, medium, high, critical) |
| `vulnerability_id` | CVE or advisory ID |

### psalm

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed) |
| `cwe` | CWE ID of the taint type |
| `file_path` | PHP source file path |
| `finding_type` | Type of finding (vulnerability) |
| `rule_id` | Taint rule ID (TaintedSql, TaintedXss, etc.) |
| `severity` | Severity level (low, medium, high) |

### retire

| Field | Description |
|---|---|
| `ecosystem` | Package ecosystem (npm) |
| `file_path` | Path to the JS file containing the vulnerable library |
| `finding_type` | Type of finding (dependency) |
| `package_name` | Name of the vulnerable JavaScript library |
| `package_version` | Version of the vulnerable library detected |
| `severity` | Severity level (low, medium, high, critical) |
| `vulnerability_id` | CVE ID |

### semgrep

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed, probable, potential) |
| `cwe` | CWE ID from rule metadata |
| `file_path` | Source file path where the pattern matched |
| `finding_type` | Type of finding (vulnerability) |
| `rule_id` | Semgrep rule ID |
| `severity` | Severity level (low, medium, high) |

### sqlmap

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed, probable, potential) |
| `cwe_id` | CWE ID (89 for SQL injection) |
| `dbms` | Database management system detected |
| `finding_type` | Type of finding (vulnerability) |
| `method` | HTTP method used in the injection (GET, POST, etc.) |
| `param` | Parameter that is vulnerable to SQL injection |
| `payload` | SQL injection payload used |
| `severity` | Severity level |
| `technique_summary` | Summary of injection techniques detected |
| `url` | Target URL where SQL injection was found |

### xsstrike

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed, probable, potential) |
| `cwe` | CWE ID (79 for XSS) |
| `description` | Description of vulnerable component (for component findings) |
| `finding_type` | Type of finding (vulnerability or dependency) |
| `package_name` | Package name (for component findings) |
| `package_version` | Package version (for component findings) |
| `param` | Parameter vulnerable to XSS |
| `payload` | XSS payload used |
| `severity` | Severity level (low, medium, high, critical) |
| `url` | URL or component location |
| `vulnerability_id` | CVE ID (for component findings) |

### zap

| Field | Description |
|---|---|
| `confidence` | Confidence level (confirmed, probable, potential) |
| `cwe` | CWE ID from the ZAP alert |
| `finding_type` | Type of finding (vulnerability) |
| `method` | HTTP method used in the request |
| `severity` | Severity level (informational, low, medium, high) |
| `url` | URL where the vulnerability was detected |

---

## Tool Detection

Tally calls `check_system_tools()` on startup and when you run the `tools` REPL command.
Three detection strategies are used:

1. **PATH lookup** (`shutil.which`). Used by most tools (semgrep, gitleaks, osv-scanner, pip-audit, npm-audit, composer-audit). A tool is available if its binary is on `$PATH`.
2. **Configured path** (`Path.exists`). Used by OWASP ZAP. Checks the absolute path set in `config/commands.json` (e.g. `/usr/share/zaproxy/zap.sh`), which allows ZAP to be detected even when not on `$PATH`.
3. **Python import** (`importlib.util.find_spec`). Used by tree-sitter. Checks that `tree_sitter` and `tree_sitter_language_pack` are importable in the active environment.
