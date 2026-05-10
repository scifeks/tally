# CLI Exit Codes

Every `tally-cli.py` command exits with a numeric code you can use in scripts and CI/CD pipelines.

## Exit Code Table

| Code | Name | Meaning |
|------|------|---------|
| 0 | Success | Command completed without errors |
| 1 | General error | Unexpected failure, I/O error, or service unavailable |
| 2 | Invalid arguments | Mutually exclusive flags, unknown tool or repo names, bad values |
| 3 | Project not found | `--project` not specified or the named project does not exist |

---

## When Each Code Applies

### Exit 0: Success

The command ran to completion. For `scan`, all requested tools executed (individual tool failures within a scan do not change the exit code). For `purge`, deletion completed. For `stats`, statistics were printed.

### Exit 1: General error

Covers runtime failures that are not argument or project errors:

- RAG engine unavailable (ChromaDB or embedding provider not reachable)
- Scan already in progress (`JobBusy`)
- Docker not available (triage commands)
- PDF rendering failure
- Unexpected exceptions

### Exit 2: Invalid arguments

The arguments are syntactically valid but semantically wrong:

- `--tool` and `--skip-tools` both specified on `scan`
- Unknown tool name passed to `--tool`, `--skip-tools`, or `purge --tool`
- Unknown repository name passed to `--repo`
- Unknown domain passed to `--domain`

### Exit 3: Project not found

- `--project` flag was omitted on a command that requires it
- The named project does not exist in the registry
- The named project has been archived

---

## Examples

```bash
# Successful scan
python3 tally-cli.py --project=myapp scan --skip-enrichment
echo $?  # 0

# Missing project flag
python3 tally-cli.py scan
echo $?  # 3

# Nonexistent project
python3 tally-cli.py --project=missing stats
echo $?  # 3

# Mutually exclusive flags
python3 tally-cli.py --project=myapp scan --tool=semgrep --skip-tools=gitleaks
echo $?  # 2

# Unknown tool name
python3 tally-cli.py --project=myapp scan --tool=nonexistent
echo $?  # 2
```
