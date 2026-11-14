---
name: tally-scan-ssrf
description: >
  Scan the target repo for server-side request forgery defects. Detects
  HTTP client calls, URL fetchers, and network requests that accept
  user-controlled URLs without allowlist validation or domain
  restriction. Emits findings shaped for Tally MCP submission (rule_id
  `ssrf`, CWE-918, severity high). Invoke when the user says "SSRF",
  "server-side request forgery", "check for SSRF", or when dispatched
  by `tally-scan-external`.
---

# Tally scanner: SSRF

Detects sinks where user-controlled URLs reach network request APIs
without URL validation. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `ssrf` |
| Primary CWE | `CWE-918` |
| OWASP 2025 category | `Insecure Design` |
| Default severity | `high` |
| Parent label (dedup) | `SSRF` |


## Detection matrix

### Python

- **requests library**: `requests.get(user_url)`,
  `requests.post(params['webhook_url'])`,
  `requests.put(request.data['url'])` without domain validation.
- **urllib and urllib3**: `urllib.request.urlopen(
  request.args['url'])`, `urllib3.PoolManager().request('GET',
  user_url)` without allowlist checking.
- **httpx**: `httpx.get(params['callback'])`,
  `httpx.AsyncClient().get(user_supplied_url)` without domain
  restriction.
- **aiohttp**: `aiohttp.ClientSession().get(user_url)` without
  allowlist validation.
- **Any HTTP client with user-sourced URL**: socket, httplib,
  telnetlib reaching a sink that accepts a URL string from user
  input.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **file_get_contents with URL**: `file_get_contents(
  $_POST['url'])`, `file_get_contents($request->input('url'))`
  without domain check (stream wrappers enabled).
- **curl functions**: `curl_setopt($ch, CURLOPT_URL,
  $_POST['url'])`, `curl_exec($ch)` where the URL is user-controlled
  without validation.
- **Laravel HTTP client**: `Http::get($request->input('url'))`
  without allowlist.
- **Guzzle**: `$client->request('GET', $userUrl)` without domain
  validation.
- **fopen with URL wrappers**: `fopen($user_url, 'r')` where URL
  wrappers are enabled.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **fetch API**: `fetch(req.body.url)`, `fetch(req.query.webhookUrl)`
  without allowlist validation.
- **axios**: `axios.get(req.body.callbackUrl)`,
  `axios.post(params.redirect_uri)` without domain check.
- **got**: `got(req.body.callback)` without URL validation.
- **node-fetch**: `node-fetch(req.body.imageUrl)` without allowlist.
- **http/https stdlib**: `http.get(userUrl)`,
  `https.request(userUrl)` without domain restriction.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **NestJS HttpService**: `this.httpService.get(dto.url)` without
  domain validation.
- **axios with TypeScript**: `axios.get(req.body.url as string)`
  without allowlist.
- **fetch**: `fetch(config.webhookUrl)` where `webhookUrl` comes
  from user input without validation.
- **undici**: `undici.request(userUrl)` without domain validation.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is an
  SSRF at this location.
- When the taint source is in the same file: `meta.taint_source`
  naming the request parameter or upstream variable that reaches the
  sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler
  to the sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is
  clearly a variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not
  obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`ssrf`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what
    an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-918"],
  "finding_type": ["vulnerability"],
  "rule_id": "ssrf",
  "meta": {
    "title": "<short human title, e.g. 'SSRF via webhook URL
      parameter'>",
    "owasp_name": "Insecure Design",
    "remediation": "<per-finding; see remediation
      guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
      traceable>",
    "reasoning": "<one sentence explaining the defect at this
      location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library observed in the code. Examples of good remediation
strings:

- **requests (Python)**: `Validate the URL against a domain
  allowlist before calling requests.get(). Parse the URL with
  urllib.parse.urlparse() and check the hostname against a set of
  approved domains. Block requests to private IP ranges
  (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16) using
  the ipaddress module.`
- **PHP curl**: `Validate the URL against a domain allowlist before
  curl_setopt(). Use filter_var() with FILTER_VALIDATE_IP and
  FILTER_FLAG_NO_PRIV_RANGE to reject private IPs. Alternatively,
  maintain a list of approved domains and verify the parsed URL
  hostname against it.`
- **Node.js fetch**: `Validate the URL against a domain allowlist
  before calling fetch(). Use new URL() to parse the URL and check
  the hostname. Reject private IP addresses (127.0.0.0/8,
  192.168.0.0/16, ::1/128) explicitly.`
- **NestJS HttpService**: `Inject a URL validator into the service
  that checks the hostname against an allowlist. Use url.parse()
  before invoking httpService.get(), and reject any URL with a
  private or reserved IP.`

Keep it two to four sentences. Vague guidance ("validate the URL")
is worse than no guidance.

## Common false positives

- **Static configuration URLs**: `requests.get(config.webhook_url)`
  where `webhook_url` is from a config file (not user input per
  request) is safe. Confirm the value is not later overridden by
  user input.
- **Allowlisted URLs**: `if url in APPROVED_WEBHOOKS:
  requests.get(url)` is safe if `APPROVED_WEBHOOKS` is a fixed set
  with no user-supplied entries.
- **URL construction from safe parts**: `fetch(
  'https://api.trusted-domain.com/path?q=' + sanitized_param)` is
  safe if the domain is hardcoded and only the query parameter
  varies.
- **Internal service calls**: `requests.get('http://localhost:8080/
  webhook', json=data)` where the hostname is hardcoded to a local
  service is safe (though defense-in-depth would still restrict it).
- **URL validation present**: If the same file contains a validation
  function checking the URL against an allowlist, and the sink calls
  that function before making the request, do not flag it.

## References

- `references/python.md`: Python patterns for requests, urllib,
  httpx, aiohttp.
- `references/php.md`: PHP patterns for file_get_contents, curl,
  Laravel HTTP, Guzzle, fopen.
- `references/javascript.md`: Node patterns for fetch, axios, got,
  node-fetch, http/https stdlib.
- `references/typescript.md`: TypeScript patterns for NestJS, axios,
  fetch, undici.
