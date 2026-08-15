# JavaScript missing security headers patterns

Vulnerable-vs-safe snippets for Node.js web frameworks the
`misconfig.security_headers` scanner recognizes. When multiple safe forms
exist, the canonical one is shown first.

## Express without helmet

### Vulnerable

```javascript
const express = require('express');
const app = express();

app.get('/api/user', (req, res) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

### Safe

```javascript
const express = require('express');
const helmet = require('helmet');
const app = express();

app.use(helmet({
    hsts: { maxAge: 31536000, includeSubDomains: true },
    frameguard: { action: 'deny' },
    contentSecurityPolicy: false
}));

app.get('/api/user', (req, res) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

Install helmet with npm install helmet. Call app.use(helmet()) without
disabling individual protections. Helmet sets X-Content-Type-Options,
X-Frame-Options, Strict-Transport-Security, and Referrer-Policy headers
on all responses by default.

## Express with helmet disabled protections

### Vulnerable

```javascript
const express = require('express');
const helmet = require('helmet');
const app = express();

app.use(helmet({
    hsts: false,
    frameguard: false,
    contentSecurityPolicy: false
}));

app.get('/api/user', (req, res) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

### Safe

```javascript
const express = require('express');
const helmet = require('helmet');
const app = express();

app.use(helmet());

app.get('/api/user', (req, res) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

Call helmet() without options or with options that enable all protections.
Do not set hsts, frameguard, or other protections to false unless there is
a documented reason to disable them.

## Koa without koa-helmet

### Vulnerable

```javascript
const Koa = require('koa');
const Router = require('koa-router');
const app = new Koa();
const router = new Router();

router.get('/api/user', (ctx) => {
    ctx.body = { id: 1, name: 'Alice' };
});

app.use(router.routes());
app.listen(3000);
```

### Safe

```javascript
const Koa = require('koa');
const Router = require('koa-router');
const helmet = require('koa-helmet');
const app = new Koa();
const router = new Router();

app.use(helmet({
    hsts: { maxAge: 31536000, includeSubDomains: true },
    frameguard: { action: 'deny' }
}));

router.get('/api/user', (ctx) => {
    ctx.body = { id: 1, name: 'Alice' };
});

app.use(router.routes());
app.listen(3000);
```

Install koa-helmet with npm install koa-helmet. Call app.use(helmet())
before registering routes. The middleware automatically injects security
headers on all responses.

## Fastify without @fastify/helmet

### Vulnerable

```javascript
const fastify = require('fastify')();

fastify.get('/api/user', (request, reply) => {
    reply.send({ id: 1, name: 'Alice' });
});

fastify.listen({ port: 3000 });
```

### Safe

```javascript
const fastify = require('fastify')();
const helmet = require('@fastify/helmet');

fastify.register(helmet, {
    contentSecurityPolicy: false,
    hsts: { maxAge: 31536000, includeSubDomains: true },
    frameguard: { action: 'deny' }
});

fastify.get('/api/user', (request, reply) => {
    reply.send({ id: 1, name: 'Alice' });
});

fastify.listen({ port: 3000 });
```

Install @fastify/helmet with npm install @fastify/helmet. Register the
plugin with fastify.register(helmet) before starting the server. The
plugin sets X-Content-Type-Options, X-Frame-Options,
Strict-Transport-Security, and Referrer-Policy headers on all responses.

## Custom middleware missing headers

### Vulnerable

```javascript
const express = require('express');
const app = express();

app.use((req, res, next) => {
    res.setHeader('X-Custom-Header', 'value');
    next();
});

app.get('/api/user', (req, res) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

### Safe

```javascript
const express = require('express');
const app = express();

app.use((req, res, next) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader(
        'Strict-Transport-Security',
        'max-age=31536000; includeSubDomains'
    );
    res.setHeader(
        'Referrer-Policy',
        'strict-origin-when-cross-origin'
    );
    res.setHeader('X-Custom-Header', 'value');
    next();
});

app.get('/api/user', (req, res) => {
    res.json({ id: 1, name: 'Alice' });
});

app.listen(3000);
```

If writing custom middleware, call res.setHeader() to add
X-Content-Type-Options, X-Frame-Options, Strict-Transport-Security, and
Referrer-Policy headers. Register the middleware globally using
app.use() before defining routes.
