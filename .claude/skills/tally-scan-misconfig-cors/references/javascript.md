# JavaScript CORS misconfiguration patterns

Vulnerable-vs-safe snippets for Node.js web frameworks the `misconfig.cors`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## Express cors middleware

### Vulnerable

```javascript
const express = require('express');
const cors = require('cors');
const app = express();

app.use(cors({origin: '*', credentials: true}));
```

```javascript
app.use(cors({origin: true, credentials: true}));
```

### Safe

```javascript
const express = require('express');
const cors = require('cors');
const app = express();

const allowedOrigins = [
  'https://app.example.com',
  'https://trusted-partner.example.com',
];

app.use(cors({
  origin: allowedOrigins,
  credentials: true,
}));
```

Pass an explicit list of allowed origins to the cors middleware. Wildcard
origin with credentials is rejected by browsers but signals misconfiguration.

## Express manual header reflection

### Vulnerable

```javascript
app.get('/api/data', (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin);
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  res.json({data: 'sensitive'});
});
```

### Safe

```javascript
const allowedOrigins = [
  'https://app.example.com',
  'https://trusted-partner.example.com',
];

app.get('/api/data', (req, res) => {
  if (allowedOrigins.includes(req.headers.origin)) {
    res.setHeader('Access-Control-Allow-Origin', req.headers.origin);
    res.setHeader('Access-Control-Allow-Credentials', 'true');
  } else {
    res.status(403).send('Origin not allowed');
  }
  res.json({data: 'sensitive'});
});
```

Validate the Origin header against an allowlist before reflecting it into
the response. Never reflect an unvalidated origin.

## Koa CORS middleware

### Vulnerable

```javascript
const Koa = require('koa');
const cors = require('@koa/cors');
const app = new Koa();

app.use(cors({origin: '*', credentials: true}));
```

### Safe

```javascript
const Koa = require('koa');
const cors = require('@koa/cors');
const app = new Koa();

const allowedOrigins = [
  'https://app.example.com',
  'https://trusted-partner.example.com',
];

app.use(cors({
  origin: (ctx) => {
    if (allowedOrigins.includes(ctx.request.origin)) {
      return ctx.request.origin;
    }
    return false;
  },
  credentials: true,
}));
```

Use the origin validation function to check the origin against an allowlist.
The @koa/cors module supports a callback to validate origins dynamically.

## Manual wildcard header

### Vulnerable

```javascript
app.get('/api/data', (req, res) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
  res.header('Access-Control-Allow-Credentials', 'true');
  res.json({data: 'sensitive'});
});
```

### Safe

```javascript
const allowedOrigins = ['https://app.example.com'];

app.get('/api/data', (req, res) => {
  if (allowedOrigins.includes(req.headers.origin)) {
    res.header('Access-Control-Allow-Origin', req.headers.origin);
    res.header('Access-Control-Allow-Methods', 'GET, POST');
    res.header('Access-Control-Allow-Credentials', 'true');
  } else {
    res.status(403).send('Forbidden');
  }
  res.json({data: 'sensitive'});
});
```

Never set wildcard origin with credentials enabled. Enumerate allowed origins
and validate incoming requests before setting response headers.
