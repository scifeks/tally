# URL Discovery

Tally uses a multi-source URL discovery pipeline to build the list of endpoints
that DAST tools (ZAP, XSStrike, DalFox) will test. Three sources contribute to
this list — Katana, Noir, and a user-provided endpoint file. All three are
optional and composable: any subset can be active for a given repository, and
their outputs are merged automatically before each scan.

## Pipeline overview

```
Katana (runtime crawl)  ──┐
Noir (static analysis)  ──┼──► URLMerger (deduplicate + scope-filter)
User endpoint file      ──┘         │
                                    ├──► seeds.txt      (XSStrike, DalFox)
                                    └──► merged_oas3.json  (ZAP)
```

Merge priority is Katana → Noir → user file. Deduplication preserves first-seen
order and is scheme-insensitive (http and https on the same path collapse to one
entry). Out-of-scope URLs (different host:port from `base_urls[0]`) are dropped
before the merged outputs are written.

The merged outputs are persisted to disk and their paths written back to
`repositories.json` (`merged_seeds_path`, `merged_oas3_path`) so that
subsequent tool runs can consume them without re-running discovery.

---

## Katana — runtime crawler

[ProjectDiscovery Katana](https://github.com/projectdiscovery/katana) crawls a
live application by following links, extracting XHR/fetch endpoints, and
optionally rendering JavaScript via a headless Chrome browser.

**Requires:** `base_urls` to be configured for the repository. Katana is skipped
when `base_urls` is empty.

### Configuration

| Field | Default | Description |
|-------|---------|-------------|
| `katana_headless` | `false` | Enable headless Chrome (`-hl`). Discovers JS-rendered routes but drops session cookies on some apps and can hang on others. |
| `katana_depth` | `5` | Crawl depth (`-d`). Capped at 5 when `katana_headless` is true. |
| `katana_headers` | `{}` | Extra HTTP headers injected via `-H`. Use for manual cookie injection. |
| `auth` | `null` | Structured auth block — see [Authentication](#authentication). |

Set these fields during `repo add` / `repo edit`, or edit `repositories.json`
directly.

### Headless vs non-headless

Headless mode (`katana_headless: true`) launches a real Chrome instance so that
JavaScript-rendered routes and SPA endpoints are visible to the crawler. Use it
for Single Page Apps (React, Vue, Angular).

Non-headless mode (`katana_headless: false`) uses plain HTTP requests (fast,
no Chrome dependency). Use it for server-rendered apps and any app that sets
session cookies via the login form — Chrome-based crawlers can silently drop
session cookies on some backends.

**Known issue:** headless Katana can hang indefinitely on apps that return
cyclic parameterised URLs (e.g. `?id=1`, `?id=2`, …). The crawler has a
hard ceiling of 900 seconds (`-ct 900`), after which the process is killed.
If you see Katana timing out, try disabling headless mode.

### Authentication

For apps that require login before crawling, Tally can perform a pre-crawl
form login, extract the session cookie, and inject it into Katana
automatically.

#### How it works

1. Tally sends a GET to `login_url` and extracts any hidden form inputs
   (CSRF tokens, etc.).
2. It POSTs the login form with the resolved credentials plus any
   `extra_fields`.
3. It extracts the session cookie from the response jar and injects it into
   Katana via `-H "Cookie: ..."`, merged with any manually configured
   `katana_headers`.

#### Configuring auth in the REPL

Auth is configured as part of `repo add` or `repo edit`. Tally asks:

```
  Does this site require login to crawl? [y/N]:
```

Answering `y` opens the auth sub-interview:

```
  Login URL: http://myapp.local/login
  Username field name [username]:
  Password field name [password]:
  Credentials: set an env var (e.g. MY_APP_CREDS=user:pass) or enter them inline.
  Env var takes precedence when both are set.
  Credentials env var name (optional): MY_APP_CREDS
  Inline username (optional fallback):
  Inline password (optional fallback):
```

- **Login URL** — the full URL of the HTML login form (the page that contains
  the `<form>` with username and password inputs).
- **Username / password field names** — the `name` attribute of each input.
  Default values (`username`, `password`) work for most apps; inspect the
  page source if the app uses non-standard names.
- **Credentials env var** — the name of a shell environment variable that
  holds credentials in `user:pass` format. Tally stores only the variable
  *name* in config — the credentials themselves are never written to disk.
- **Inline username / password** — a plaintext fallback stored directly in
  `repositories.json`. See the security note below before using these.

To remove auth from a repository, run `repo edit <name>` and answer `n` to
the login prompt.

To add `extra_fields` (e.g. a submit button value that the form requires),
edit `repositories.json` directly — the wizard does not prompt for them.
See [Editing config directly](#editing-config-directly) below.

#### Credential resolution order

At scan time, credentials are resolved in this order:

1. If `credentials_env` is set **and the named env var is present in the
   shell**, it is parsed as `username:password` (split on the first colon).
2. If `credentials_env` is unset or the env var is absent, and both `username`
   and `password` are non-empty in config, those inline values are used.
3. If neither source yields credentials, the login step is skipped, Katana
   crawls without authentication, and a warning is written to the log file.
   **No error is shown in the REPL** — Katana runs, it just crawls as an
   anonymous user.

#### Credential security

**`credentials_env` (recommended).** Only the variable name is stored in
`repositories.json`. The credentials live exclusively in your shell
environment and are never written to disk by Tally.

To use this approach, export the variable before starting Tally:

```bash
export MY_APP_CREDS="myuser:mypassword"
.venv/bin/python3 tally.py
```

The env var is not persisted across shell restarts. To avoid re-exporting it
every session, add the export to your shell profile (`~/.bashrc`,
`~/.zshrc`, etc.) or source a local `.env` file before running Tally.

**If the env var is gone after a restart:** If `credentials_env` is set in
config but the named variable is not present in the shell, and no inline
credentials are configured, Tally silently falls back to unauthenticated
crawling. The REPL shows no error. If Katana returns far fewer endpoints than
expected, check that the env var is exported in the current shell.

**Inline `username` / `password` (convenience only).** These values are stored
as plaintext in `repositories.json`. Do not use them if `repositories.json`
is version-controlled or shared, as real credentials will be committed and
exposed. Use inline credentials only for isolated local testing where the
config file never leaves your machine.

#### Editing config directly

The `auth` block in `repositories.json` looks like this:

```json
"auth": {
  "login_url": "http://myapp.local/login",
  "username_field": "username",
  "password_field": "password",
  "extra_fields": {},
  "credentials_env": "MY_APP_CREDS",
  "username": "",
  "password": ""
}
```

`extra_fields` accepts arbitrary key-value pairs that are included in the
POST body alongside the credentials. Use it for apps that require a submit
button value or a hidden field that is not automatically extracted from the
page (e.g. `{"Login": "Login"}`).

To disable auth entirely, remove the `auth` key or set it to `null`.

---

## Noir — static endpoint discovery

[OWASP Noir](https://github.com/noir-cr/noir) analyses source code and emits an
OAS3 spec listing all API endpoints it can identify by static analysis. Tally
runs Noir before ZAP so that ZAP can import the spec via `-openapifile` instead
of relying on spider-only discovery.

**Requires:** a local repository path (`path` field). Noir is a pre-DAST step
and does not need the application to be running.

### When Noir is skipped

Noir is skipped automatically in any of the following cases:

| Condition | Skip message |
|-----------|-------------|
| `package.json` present at repo root (Node.js app) | `skipped (Node.js app)` |
| `dependencies_file` lists an unsupported framework (see below) | `skipped (unsupported framework (<name>))` |
| `oas3_path` is configured (user-provided endpoint file) | `skipped (endpoint file configured)` |

**Unsupported Python frameworks** detected via `dependencies_file`:
`aiohttp`, `bottle`, `cherrypy`, `falcon`, `pyramid`.

Noir v0.25.1 has no parser for these frameworks. When they are present, Noir
falls back to scanning all source files and emits spurious short-path endpoints
(`/a`, `/b`, `/0x`, …) rather than real routes. Tally detects this by reading
the repository's `dependencies_file` and skips Noir if an unsupported package
is found.

**Node.js limitation:** Noir's JavaScript parser has a known defect that causes
it to loop indefinitely on complex Node.js codebases. Tally detects Node.js
apps automatically by the presence of `package.json` at the repo root and
skips Noir for them.

### Vendor / dependency directory filtering

Noir can emit endpoints from vendored code (e.g. `/vendor/`, `/node_modules/`,
`/venv/`). Tally's Noir wrapper detects dependency directories by inspecting
lock files and passes path-prefix exclusions to Noir automatically, so vendor
endpoints are stripped before the OAS3 output is written.

### When Noir finds 0 endpoints

After a successful Noir run, if 0 endpoints are discovered, Tally prints:

```
⚠ noir found 0 endpoints. The framework may not be supported by noir.
  ZAP will fall back to spider-only mode for this repository.
```

ZAP still runs in this case using spider-only discovery. If you expected
endpoints, check that the framework appears in the
[supported tech list](https://github.com/noir-cr/noir?tab=readme-ov-file#supported-technologies)
or configure a user-provided endpoint file instead.

---

## User-provided endpoint file

You can supply your own API specification instead of (or in addition to) Katana
and Noir output. Supported formats: OAS3, OAS2/Swagger, Postman Collection
v2/v2.1, HAR.

Tally converts the file to OAS3, stores it under the project directory, and
includes it as a URL source in the merge pipeline. It does **not** replace
Katana output — both are merged.

See [docs/endpoint-files.md](endpoint-files.md) for full setup instructions,
supported formats, and conversion details.

---

## How sources are merged

After each Katana or Noir run, the URL discovery pipeline fires automatically:

1. **Read** — the merger reads the most recent OAS3 file from each tool's output
   directory (`tool_outputs/katana/<repo>_*_oas3.json`,
   `tool_outputs/noir/<repo>_*_oas3.json`), plus the user-provided endpoint file
   if `oas3_path` is set.
2. **Join** — URI paths from Noir and user files are joined with `base_urls[0]`
   to produce full URLs. Katana OAS3 entries already contain full URLs.
3. **Scope filter** — URLs whose host:port differs from `base_urls[0]` are
   dropped. This prevents crawl bleed from third-party hosts.
4. **Deduplicate** — URLs are normalised (lowercase host, strip default ports,
   strip trailing slashes, scheme-insensitive) and deduplicated in order:
   Katana first, then Noir, then user file.
5. **Write outputs:**
   - `projects/<project>/endpoints/<repo>/merged_urls.txt` — one URL per line,
     consumed by XSStrike and DalFox.
   - `projects/<project>/endpoints/<repo>/merged_oas3.json` — minimal OAS3
     document with one GET operation per unique path, consumed by ZAP via
     `-openapifile`.
6. **Persist** — `merged_seeds_path` and `merged_oas3_path` are written back to
   `repositories.json` so subsequent tool runs can consume the outputs without
   re-running discovery.

---

## Downstream consumers

| Tool | Consumes | Fallback when missing |
|------|----------|-----------------------|
| ZAP | `merged_oas3_path` (`-openapifile`) | Spider-only quickscan mode |
| XSStrike | `merged_seeds_path` (URL list) | Crawls from `base_url` directly |
| DalFox | `merged_seeds_path` (URL list) | Skipped (no seed list = no targets) |

---

## Debugging low URL counts

If DAST tools are testing fewer URLs than expected:

1. **Check Katana output** — look at
   `projects/<project>/tool_outputs/katana/<repo>_*.jsonl`. If it is empty or
   very short, the crawl may have run without auth (see
   [Authentication](#authentication)) or headless mode may have dropped the
   session cookie.

2. **Check if Noir was skipped** — scan output lines like
   `skipped (unsupported framework (aiohttp))` explain why Noir produced nothing.

3. **Check the merged output** — inspect
   `projects/<project>/endpoints/<repo>/merged_urls.txt` to see exactly what
   URLs are being passed to scanners.

4. **Try a user-provided endpoint file** — if both Katana and Noir produce
   sparse results, supply an OAS3/Postman/HAR file directly. See
   [docs/endpoint-files.md](endpoint-files.md).
