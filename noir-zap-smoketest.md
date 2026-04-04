# Noir → ZAP Smoketest Results

**Date:** 2026-04-03  
**Branch:** TAL-104  
**Target:** DVNA (Damn Vulnerable Node App) at `http://localhost:9090`  
**Source:** `/llm/code/repos/node/dvna`

---

## Step 1: Noir static endpoint discovery

**Command:**
```
/usr/bin/noir -b /llm/code/repos/node/dvna -f oas3 --no-log -o /tmp/dvna_oas3.json
```

**Exit code:** 0  
**Result:** PASS

**Endpoints discovered:**

| Metric | Value |
|---|---|
| Total paths | 27 |
| Total endpoints (path × method) | 38 |

**Sample endpoints:**

| Method | Path | Params |
|---|---|---|
| GET | `/login` | — |
| POST | `/login` | — |
| GET | `/learn/vulnerability/{vuln}` | path: `vuln` |
| GET | `/bulkproducts` | query: `legacy` |
| POST | `/bulkproducts` | — |
| GET | `/admin/users` | — |
| GET | `/usersearch` | — |
| POST | `/usersearch` | — |
| GET | `/calc` | — |
| POST | `/calc` | — |
| POST | `/register` | — |
| GET | `/forgotpw` | — |
| POST | `/forgotpw` | — |
| GET | `/resetpw` | — |
| POST | `/resetpw` | — |

**OAS3 validity check:** `openapi: "3.0.3"` — valid ✓  
**Parser round-trip:** `parse_noir_json()` returned 27 paths, 38 endpoints — matches raw doc ✓

---

## Step 2: ZAP DAST scan with OAS3 input

**Command:**
```
/usr/share/zaproxy/zap.sh -cmd \
  -openapifile /tmp/dvna_oas3.json \
  -openapitargeturl http://127.0.0.1:9090 \
  -quickurl http://127.0.0.1:9090/login \
  -quickprogress \
  -quickout /tmp/zap_report.json
```

**Exit code:** 0  
**Result:** PASS  
**Report written:** yes (37 KB JSON)

**Alert summary:**

| Risk | Count |
|---|---|
| Medium | 17 |
| Low | 18 |
| **Total** | **35** |

**Notable alerts:**

| Risk | Alert |
|---|---|
| Medium | Absence of Anti-CSRF Tokens (`/login`, `/register`, `/forgotpw`) |
| Medium | Content Security Policy (CSP) Header Not Set |
| Medium | Vulnerable JS Library (jQuery 3.2.1) |
| Medium | Sub Resource Integrity Attribute Missing |
| Low | Cookie without SameSite Attribute |
| Low | Server Leaks Information via `X-Powered-By` header |
| Low | X-Content-Type-Options Header Missing |

---

## Step 3: Assertion checklist

| Assertion | Result |
|---|---|
| Noir found ≥ 1 endpoint | ✓ (38 found) |
| OAS3 document is valid (openapi: 3.x) | ✓ (3.0.3) |
| Parser round-trip produces correct endpoint count | ✓ (38 == raw path×method product) |
| ZAP accepted `-openapifile` without errors | ✓ (exit 0) |
| ZAP produced a report file | ✓ (37 KB) |
| ZAP found ≥ 1 alert | ✓ (35 alerts) |

**All assertions: PASS**

---

## Notes

- **`-quickurl` required alongside `-openapifile`:** Without `-quickurl`, ZAP imports the OAS3
  spec and exits immediately without running the spider or active scan, writing no report.
  The ZAP `build_command` in OpenAPI mode now correctly includes both flags.

- **OAS3 file preservation:** Noir's output file is not deleted after ingestion so that ZAP
  can consume it in the subsequent scan pass.

- **Discovered vs ZAP-scanned endpoints:** Noir discovers 38 endpoints statically.
  ZAP crawled additional paths (via traditional spider) that were not in the OAS3 spec
  (e.g. `/robots.txt`, `/sitemap.xml`, static assets). The OAS3 spec ensures that API-only
  paths with no HTML links (like `/admin/users`, `/useredit`, `/calc`) are included in
  the scan even if the spider would not reach them from the starting URL.
