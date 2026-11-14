# JavaScript data integrity verification patterns

Vulnerable-vs-safe snippets for the Node.js HTTP, webhook, JWT, and dynamic
import patterns the `data_integrity.missing_integrity_verification` scanner
recognizes.

## fetch: HTTP artifact download

### Vulnerable

```javascript
const response = await fetch(
  "https://trusted-domain.com/plugin.js"
);
const code = await response.text();
eval(code);
```

### Safe

```javascript
const crypto = require("crypto");

const response = await fetch(
  "https://trusted-domain.com/plugin.js"
);
const code = await response.text();
const expectedHash = "abc123def456...";
const actualHash = crypto.createHash("sha256").update(code).digest("hex");
if (actualHash !== expectedHash) {
  throw new Error("Hash mismatch");
}
eval(code);
```

Compute the SHA256 hash of the downloaded content using `crypto.createHash()`,
compare it to the known-good hash, and reject if they do not match.

## axios: HTTP artifact download

### Vulnerable

```javascript
const axios = require("axios");

const response = await axios.get("https://trusted-domain.com/config.json");
const config = response.data;
applyConfig(config);
```

### Safe

```javascript
const axios = require("axios");
const crypto = require("crypto");

const response = await axios.get("https://trusted-domain.com/config.json");
const content = JSON.stringify(response.data);
const expectedHash = "def789ghi012...";
const actualHash = crypto.createHash("sha256").update(content).digest("hex");
if (actualHash !== expectedHash) {
  throw new Error("Hash mismatch");
}
const config = response.data;
applyConfig(config);
```

Always verify the hash of downloaded data before using it. For JSON responses,
serialize the JSON again to compute the hash consistently.

## Express: Webhook signature verification

### Vulnerable

```javascript
app.post("/webhook", express.json(), (req, res) => {
  const data = req.body;
  processOrder(data);
  res.json({status: "ok"});
});
```

### Safe

```javascript
const crypto = require("crypto");
const express = require("express");

const verifyWebhookSignature = (req, res, next) => {
  const signature = req.headers["x-hub-signature-256"];
  if (!signature) {
    return res.status(401).json({error: "Missing signature"});
  }
  const secret = process.env.WEBHOOK_SECRET;
  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(req.rawBody)
    .digest("hex");
  if (!crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  )) {
    return res.status(401).json({error: "Invalid signature"});
  }
  next();
};

app.use(express.raw({type: "application/json"}));
app.post("/webhook", verifyWebhookSignature, (req, res) => {
  const data = JSON.parse(req.rawBody.toString());
  processOrder(data);
  res.json({status: "ok"});
});
```

Compute the HMAC using the raw request body (not the parsed JSON) with
`crypto.createHmac()`. Use `crypto.timingSafeEqual()` to compare the
signatures to prevent timing attacks. Extract the signature from the
request header (GitHub uses `X-Hub-Signature-256`, Stripe uses
`Stripe-Signature`, etc.).

## Koa: Webhook signature verification

### Vulnerable

```javascript
const Koa = require("koa");
const koaBody = require("koa-body");

const app = new Koa();
app.use(koaBody());
app.use(async (ctx) => {
  if (ctx.path === "/webhook") {
    const data = ctx.request.body;
    processOrder(data);
    ctx.body = {status: "ok"};
  }
});
```

### Safe

```javascript
const crypto = require("crypto");
const Koa = require("koa");
const koaBody = require("koa-body");

const verifyWebhookSignature = async (ctx, next) => {
  const signature = ctx.headers["x-hub-signature-256"];
  if (!signature) {
    ctx.status = 401;
    ctx.body = {error: "Missing signature"};
    return;
  }
  const secret = process.env.WEBHOOK_SECRET;
  const expected = "sha256=" + crypto
    .createHmac("sha256", secret)
    .update(ctx.rawBody)
    .digest("hex");
  if (!crypto.timingSafeEqual(
    Buffer.from(expected),
    Buffer.from(signature)
  )) {
    ctx.status = 401;
    ctx.body = {error: "Invalid signature"};
    return;
  }
  await next();
};

const app = new Koa();
app.use(koaBody());
app.use(async (ctx) => {
  if (ctx.path === "/webhook") {
    await verifyWebhookSignature(ctx, async () => {
      const data = ctx.request.body;
      processOrder(data);
      ctx.body = {status: "ok"};
    });
  }
});
```

Always capture and verify the raw body before parsing. Use
`crypto.timingSafeEqual()` for comparison.

## jsonwebtoken: JWT signature verification

### Vulnerable

```javascript
const jwt = require("jsonwebtoken");

const token = req.headers.authorization.replace("Bearer ", "");
const payload = jwt.decode(token);
const userId = payload.user_id;
```

### Safe

```javascript
const jwt = require("jsonwebtoken");

const token = req.headers.authorization.replace("Bearer ", "");
const secret = process.env.JWT_SECRET;
try {
  const payload = jwt.verify(token, secret, {
    algorithms: ["HS256"]
  });
  const userId = payload.user_id;
} catch (err) {
  return res.status(401).json({error: "Invalid token"});
}
```

Always use `jwt.verify()` (not `jwt.decode()`) and specify an explicit
`algorithms` array. Never allow `"none"` in the algorithms list. Use a
secret from an environment variable, never hardcoded.

## Dynamic module import without integrity

### Vulnerable

```javascript
const modulePath = req.query.module;
const plugin = require(modulePath);
plugin.init();
```

### Safe

```javascript
const crypto = require("crypto");

const allowedModules = {
  "plugin_v1": {
    path: "./plugins/plugin_v1.js",
    hash: "abc123def456..."
  },
  "plugin_v2": {
    path: "./plugins/plugin_v2.js",
    hash: "def789ghi012..."
  }
};

const moduleName = req.query.module;
const moduleConfig = allowedModules[moduleName];
if (!moduleConfig) {
  return res.status(400).json({error: "Unknown module"});
}
const fs = require("fs");
const content = fs.readFileSync(moduleConfig.path, "utf8");
const actualHash = crypto.createHash("sha256").update(content).digest("hex");
if (actualHash !== moduleConfig.hash) {
  throw new Error("Hash mismatch");
}
const plugin = require(moduleConfig.path);
plugin.init();
```

Maintain an allowlist of known-good modules and their hashes. Verify the
content hash before requiring.

## got: HTTP artifact download with integrity

### Vulnerable

```javascript
const got = require("got");

const response = await got("https://trusted-domain.com/data.json");
const data = JSON.parse(response.body);
process(data);
```

### Safe

```javascript
const got = require("got");
const crypto = require("crypto");

const response = await got("https://trusted-domain.com/data.json");
const expectedHash = "jkl345mno678...";
const actualHash = crypto
  .createHash("sha256")
  .update(response.body)
  .digest("hex");
if (actualHash !== expectedHash) {
  throw new Error("Hash mismatch");
}
const data = JSON.parse(response.body);
process(data);
```

Always verify the hash of downloaded content before parsing or using it.
