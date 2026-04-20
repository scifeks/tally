# Endpoint Files

When adding or editing a repository, you can supply an existing API endpoint
definition file. When configured, Tally uses that file to guide the ZAP DAST
scanner instead of running Noir to discover endpoints automatically.

## Why it exists

Noir works best for source code analysis. When an endpoint file already exists
— for example, an OAS3 spec maintained alongside the API — using it directly
gives more accurate and complete ZAP coverage than static analysis.

## Supported formats

| Format | Extensions | Conversion required |
|---|---|---|
| OAS3 (OpenAPI 3.x) | `.json`, `.yaml` | No — used directly |
| OAS2 / Swagger 2.0 | `.json`, `.yaml` | Yes — via `swagger2openapi` (npm) |
| Postman Collection v2.0 / v2.1 | `.json` | Yes — via `postman-to-openapi` (npm) |
| HAR (HTTP Archive) | `.har` | Yes — built-in Python converter |
| Katana JSONL | `.jsonl` | Yes — built-in Python converter |

---

## How to provide a file

### repo add

At the end of the `repo add` interview, Tally shows:

```
  Supported endpoint file formats: OAS3 (.json/.yaml), OAS2/Swagger (.json/.yaml), Postman Collection v2/v2.1 (.json), HAR (.har)
  Warning: when an endpoint file is configured, Noir is skipped and ZAP relies entirely on that file. ZAP results will be less accurate if the file is incomplete.
  Endpoint definition file path (optional):
```

Enter the absolute or relative path to the file, or press Enter to skip.

**On success:** the file is converted to OAS3, stored under the project
directory, and `oas3_path` is saved in `repositories.json`:

```
  ✓ Endpoint file converted: /path/to/projects/<project>/endpoints/endpoints.json
✓ Repository '<name>' added to project '<project>'
```

**On failure:** the error is printed and the repository is saved without an
endpoint file. You can configure one later with `repo edit`:

```
  Endpoint file conversion failed: <reason>
  Repository will be added without an endpoint file. You can add one later with 'repo edit'.
✓ Repository '<name>' added to project '<project>'
```

### repo edit

When editing a repository that already has an endpoint file configured:

```
  Current endpoint file: /path/to/projects/<project>/endpoints/endpoints.json
  Replace endpoint file? [y/N]:
```

Answering `y` deletes the existing converted file and its stored original,
then shows:

```
  Warning: when an endpoint file is configured, Noir is skipped and ZAP relies entirely on that file. ZAP results will be less accurate if the file is incomplete.
  New endpoint definition file path (optional):
```

When no endpoint file is configured, the prompt is identical to `repo add`.

**On success:**

```
  ✓ Endpoint file converted: /path/to/projects/<project>/endpoints/endpoints.json
✓ Repository '<name>' updated
```

**On failure:** the error is printed and the existing configuration is kept
unchanged.

---

## What happens during conversion

1. The original file is copied to
   `projects/<project>/endpoints/original/<filename>`.
2. The file is converted to OAS3 and written to
   `projects/<project>/endpoints/endpoints.json` — or `endpoints.yaml` /
   `endpoints.yml` for OAS3 YAML inputs, which are validated and copied as-is.
3. `oas3_path` is saved in `repositories.json` pointing to the output file.
   Scans read this field to locate the spec.

---

## Effect on scans

**Noir is skipped** for repositories that have an endpoint file configured.
The scan display shows:

```
skipped (endpoint file configured)
```

**ZAP uses the configured endpoint file** instead of looking for Noir output.
When `oas3_path` is set, ZAP imports the spec via `-openapifile` and
`-openapitargeturl` automatically — no separate Noir run is needed.

**The "run Noir first" prompt is not shown** when you run `scan --tool=zap`
for a repository that has an endpoint file configured.

---

## Node.js dependency requirement

OAS2 and Postman conversion requires Node.js and `npx`. OAS3 and HAR files
work without Node.js.

| Format | Node.js required |
|---|---|
| OAS3 (OpenAPI 3.x) | No |
| HAR | No |
| OAS2 / Swagger 2.0 | Yes |
| Postman Collection | Yes |

### Installing the converter packages

The `install.sh` setup script asks:

```
  Install npm packages for OAS2/Postman conversion? [y/N]:
```

Answer `y` to install. To install them separately at any time:

```bash
npm install -g swagger2openapi postman-to-openapi
```

### If the packages are missing at conversion time

When Node.js is not installed and you attempt to convert an OAS2/Swagger file,
Tally reports:

```
OAS2/Swagger conversion requires Node.js and npx. Install Node.js from https://nodejs.org/, then run: npx swagger2openapi --help to confirm the tool is available.
```

When Node.js is not installed and you attempt to convert a Postman collection,
Tally reports:

```
Postman collection conversion requires Node.js and npx. Install Node.js from https://nodejs.org/, then run: npx postman-to-openapi --help to confirm the tool is available.
```

Install Node.js from https://nodejs.org/, then re-run `bash install.sh` to
install the converter packages.
