# Tools

## Supported Tools

| Tool | Category | What it does |
|---|---|---|
| OWASP ZAP | DAST | Dynamic web/API security scanning |
| Semgrep | SAST | Static analysis across many languages |
| tree-sitter | SAST | AST-based code analysis (Python library) |
| Gitleaks | Secrets | Git history and working-tree secret scanning |
| osv-scanner | SCA | Dependency vulnerability scanning via OSV database |
| pip-audit | SCA | Python dependency audit (PyPI advisory database) |
| npm-audit | SCA | Node.js dependency audit |
| composer-audit | SCA | PHP Composer dependency audit |

All tools are optional — Tally skips any tool that is not detected.

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
