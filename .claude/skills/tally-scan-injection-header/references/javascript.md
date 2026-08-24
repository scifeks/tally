# JavaScript HTTP header injection patterns

Vulnerable-vs-safe snippets for the Node.js web frameworks the
`injection.header` scanner recognizes. When multiple safe forms exist,
the canonical one is shown first.

## Express (res.setHeader)

### Vulnerable

```javascript
app.get("/redirect", (req, res) => {
  const url = req.query.goto;
  res.setHeader("Location", url);
  res.send(302);
});
```

```javascript
app.get("/download", (req, res) => {
  const filename = req.query.file;
  res.setHeader("Content-Disposition", `attachment; filename=${filename}`);
  res.send(data);
});
```

### Safe

```javascript
const url = require("url");
app.get("/redirect", (req, res) => {
  const goto = req.query.goto;
  try {
    const parsed = new URL(goto);
    if (
      ["http:", "https:"].includes(parsed.protocol) &&
      ALLOWED_DOMAINS.includes(parsed.hostname)
    ) {
      res.setHeader("Location", goto);
    } else {
      res.setHeader("Location", "/");
    }
  } catch {
    res.setHeader("Location", "/");
  }
  res.send(302);
});
```

```javascript
app.get("/download", (req, res) => {
  let filename = req.query.file || "download.bin";
  filename = filename.replace(/[^a-zA-Z0-9._-]/g, "");
  if (!filename) filename = "download.bin";
  res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
  res.send(data);
});
```

In modern Node.js (v14+), `res.setHeader()` automatically removes CR/LF
from header values, but do not rely on this. Validate URLs and sanitize
filenames before setting headers. Express v5+ also enforces this at the
framework level.

## Express (res.redirect)

### Vulnerable

```javascript
app.get("/go", (req, res) => {
  const url = req.query.target;
  res.redirect(url);
});
```

### Safe

```javascript
app.get("/go", (req, res) => {
  const target = req.query.target;
  try {
    const parsed = new URL(target);
    if (
      ["http:", "https:"].includes(parsed.protocol) &&
      ALLOWED_DOMAINS.includes(parsed.hostname)
    ) {
      res.redirect(target);
    } else {
      res.redirect("/");
    }
  } catch {
    res.redirect("/");
  }
});
```

Express's `res.redirect()` is a convenience wrapper around setting the
Location header. It does not validate the URL—apply URL validation before
calling it.

## stdlib http module (writeHead)

### Vulnerable

```javascript
const http = require("http");
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost").searchParams.get("go");
  res.writeHead(302, { Location: url });
  res.end();
});
```

### Safe

```javascript
const http = require("http");
const ALLOWED_DOMAINS = ["example.com", "trusted.com"];
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://localhost").searchParams.get("go");
  let location = "/";
  try {
    const parsed = new URL(url);
    if (
      ["http:", "https:"].includes(parsed.protocol) &&
      ALLOWED_DOMAINS.includes(parsed.hostname)
    ) {
      location = url;
    }
  } catch {
    // Invalid URL; use default
  }
  res.writeHead(302, { Location: location });
  res.end();
});
```

Modern Node.js http module (v14+) strips newlines, but always validate
user input before passing to `writeHead()`.

## Set-Cookie header

### Vulnerable

```javascript
app.get("/login", (req, res) => {
  const sessionId = req.query.sid;
  res.setHeader("Set-Cookie", `sid=${sessionId}`);
  res.send("ok");
});
```

### Safe

```javascript
const crypto = require("crypto");
app.get("/login", (req, res) => {
  const sessionId = crypto.randomBytes(16).toString("hex");
  res.setHeader(
    "Set-Cookie",
    `sid=${sessionId}; HttpOnly; Secure; SameSite=Strict; Max-Age=3600`
  );
  res.send("ok");
});
```

Never use user input for cookie names or values. Generate session IDs
server-side using a CSPRNG. Always set `HttpOnly`, `Secure`, and `SameSite`
flags.

## Generic header-value filtering pattern

If you must accept user input in a header, filter it:

```javascript
function safeHeaderValue(value) {
  return String(value).replace(/[\r\n]/g, "");
}

const custom = req.query.x_custom;
res.setHeader("X-Custom", safeHeaderValue(custom));
```

This is a fallback when validation is not possible. Prefer allowlist
validation or built-in framework helpers.
