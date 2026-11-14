# JavaScript SSRF patterns

Safe and vulnerable code snippets for the JavaScript HTTP libraries the
`ssrf` scanner recognizes. When multiple safe forms exist, the
canonical one is shown first.

## fetch API

### Vulnerable

```javascript
const url = req.body.webhook_url;
const response = await fetch(url);

const userUrl = req.query.redirect;
fetch(userUrl)
  .then(res => res.json())
  .then(data => console.log(data));
```

### Safe

```javascript
const ALLOWED_DOMAINS = ["api.example.com", "webhook.service.io"];

const url = req.body.webhook_url;
const parsed = new URL(url);
if (!ALLOWED_DOMAINS.includes(parsed.hostname)) {
  throw new Error("Domain not allowlisted");
}
if (parsed.protocol === "file:") {
  throw new Error("file: protocol not allowed");
}

const response = await fetch(url);
```

To block private IP ranges:

```javascript
const ALLOWED_DOMAINS = ["api.example.com"];
const PRIVATE_IPS = [
  /^127\./,
  /^10\./,
  /^172\.(1[6-9]|2[0-9]|3[01])\./,
  /^192\.168\./,
  /^::1$/,
  /^fc00:/
];

function isPrivateIp(hostname) {
  return PRIVATE_IPS.some(pattern => pattern.test(hostname));
}

const url = req.body.webhook_url;
const parsed = new URL(url);
if (
  !ALLOWED_DOMAINS.includes(parsed.hostname) &&
  !isPrivateIp(parsed.hostname)
) {
  throw new Error("IP or domain not allowed");
}

await fetch(url);
```

## axios

### Vulnerable

```javascript
const url = req.body.callback_url;
const response = await axios.get(url);

const webhookUrl = req.query.webhook;
axios.post(webhookUrl, { status: "done" });
```

### Safe

```javascript
const ALLOWED_DOMAINS = ["webhook.service.io", "api.example.com"];

const url = req.body.callback_url;
const parsed = new URL(url);
if (!ALLOWED_DOMAINS.includes(parsed.hostname)) {
  throw new Error("Domain not allowlisted");
}

const response = await axios.get(url);
```

## got

### Vulnerable

```javascript
const userUrl = req.body.fetch_url;
const response = await got(userUrl);

got(req.query.callback)
  .then(res => console.log(res.body));
```

### Safe

```javascript
const ALLOWED = ["api.example.com"];

const userUrl = req.body.fetch_url;
const parsed = new URL(userUrl);
if (!ALLOWED.includes(parsed.hostname)) {
  throw new Error("Host not allowlisted");
}

const response = await got(userUrl);
```

## node-fetch

### Vulnerable

```javascript
import fetch from "node-fetch";

const imageUrl = req.query.image_url;
const response = await fetch(imageUrl);

const userUrl = req.body.source;
fetch(userUrl).then(r => r.buffer());
```

### Safe

```javascript
import fetch from "node-fetch";

const ALLOWED_DOMAINS = ["cdn.example.com"];

const imageUrl = req.query.image_url;
const parsed = new URL(imageUrl);
if (!ALLOWED_DOMAINS.includes(parsed.hostname)) {
  throw new Error("Domain not allowlisted");
}

const response = await fetch(imageUrl);
```

## http and https stdlib

### Vulnerable

```javascript
const http = require("http");

const userUrl = req.body.url;
http.get(userUrl, res => {
  console.log(res.statusCode);
});

const https = require("https");
const url = req.query.fetch;
https.request(url, res => {
  res.on("data", chunk => process.stdout.write(chunk));
});
```

### Safe

```javascript
const http = require("http");
const url = require("url");

const ALLOWED_DOMAINS = ["api.example.com"];

const userUrl = req.body.url;
const parsed = url.parse(userUrl);
if (!ALLOWED_DOMAINS.includes(parsed.hostname)) {
  throw new Error("Domain not allowlisted");
}

http.get(userUrl, res => {
  console.log(res.statusCode);
});
```

## Dynamic URL construction (safe only with fixed domain)

When building URLs dynamically, hardcode the domain:

```javascript
const userPath = req.query.path;
const safeUrl = `https://api.trusted.com/endpoint/${encodeURIComponent(
  userPath
)}`;
const response = await fetch(safeUrl);
```

The hardcoded domain ensures the request cannot reach arbitrary
hosts.
