# JavaScript CSP misconfiguration patterns

Vulnerable-vs-safe snippets for Node.js web frameworks the `misconfig.csp`
scanner recognizes. When multiple safe forms exist, the canonical one is
shown first.

## Express with helmet

### Vulnerable

```javascript
const express = require('express');
const helmet = require('helmet');

const app = express();
app.use(helmet({
  contentSecurityPolicy: false,
}));

// CSP is disabled
```

### Safe

```javascript
const express = require('express');
const helmet = require('helmet');

const app = express();
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "https://fonts.googleapis.com"],
    },
  },
}));
```

Enable CSP in helmet by providing a config object with restrictive directives.
Set `defaultSrc` to `["'self'"]` and add specific sources for scripts and
styles.

## Express helmet permissive

### Vulnerable

```javascript
const express = require('express');
const helmet = require('helmet');

const app = express();
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["*"],
      scriptSrc: ["*", "'unsafe-inline'"],
    },
  },
}));
```

### Safe

```javascript
const express = require('express');
const helmet = require('helmet');

const app = express();
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "https://fonts.googleapis.com"],
    },
  },
}));
```

Replace wildcard sources with `'self'`. Remove `'unsafe-inline'` and
`'unsafe-eval'` unless the application requires inline scripts or styles. Use
a nonce-based policy for inline content when possible.

## Koa with koa-helmet

### Vulnerable

```javascript
const Koa = require('koa');
const helmet = require('koa-helmet');

const app = new Koa();
// No CSP middleware is registered
```

### Safe

```javascript
const Koa = require('koa');
const helmet = require('koa-helmet');

const app = new Koa();
app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "https://fonts.googleapis.com"],
    },
  },
}));
```

Use the `koa-helmet` package to set CSP headers on all responses. Configure
CSP directives to restrict sources to `'self'` and add specific trusted
origins.

## Fastify with @fastify/helmet

### Vulnerable

```javascript
const fastify = require('fastify');
const helmet = require('@fastify/helmet');

const app = fastify();
app.register(helmet, {
  contentSecurityPolicy: false,
});

// CSP is disabled
```

### Safe

```javascript
const fastify = require('fastify');
const helmet = require('@fastify/helmet');

const app = fastify();
app.register(helmet, {
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      scriptSrc: ["'self'"],
      styleSrc: ["'self'", "https://fonts.googleapis.com"],
    },
  },
});
```

Register `@fastify/helmet` with a restrictive CSP config. Set `defaultSrc` to
`["'self'"]` and add specific sources only for required external resources.
