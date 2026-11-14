# JavaScript framework defaults patterns

Vulnerable-vs-safe snippets for JavaScript framework default settings the
`misconfig.framework_defaults` scanner recognizes. When multiple safe
forms exist, the canonical one is shown first.

## Express NODE_ENV

### Vulnerable

```javascript
// app.js (production)
const express = require('express');
const app = express();

// NODE_ENV not set, or set to development in deployment

// Deployment script:
// node app.js (missing NODE_ENV=production)
```

### Safe

```javascript
// app.js
const express = require('express');
const app = express();

// Load from environment with safe default
const isDevelopment = process.env.NODE_ENV !== 'production';

// In deployment: export NODE_ENV=production && node app.js
// Or in package.json scripts:
// "start": "NODE_ENV=production node app.js"
```

Set `NODE_ENV=production` in the deployment environment. This disables
verbose error pages and enables template caching. Never rely on the
default if `NODE_ENV` is not set.

## Express error handler

### Vulnerable

```javascript
// app.js
app.use((err, req, res, next) => {
  // Sends full stack trace to client in production
  res.status(err.status || 500).json({
    error: err.message,
    stack: err.stack  // Production risk
  });
});

// Or verbose error output
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).send(err.toString());
});
```

### Safe

```javascript
// app.js
app.use((err, req, res, next) => {
  const isDevelopment = process.env.NODE_ENV !== 'production';
  res.status(err.status || 500).json({
    message: isDevelopment ? err.message : 'Internal server error'
    // Do not send stack trace to client
  });
});

// Or use express built-in production error handler
if (process.env.NODE_ENV === 'production') {
  app.use((err, req, res, next) => {
    res.status(500).json({ message: 'Internal server error' });
  });
}
```

Never send stack traces or detailed error messages to clients in
production. Use environment checks to return safe error responses.

## Next.js debug flags

### Vulnerable

```javascript
// next.config.js (production)
module.exports = {
  productionBrowserSourceMaps: true,
  onDemandEntries: {
    maxInactiveAge: 1000  // Very low, enables debug features
  },
  experimental: {
    debug: true
  }
};

// or .next/server/lib/config.js
const isDev = true;  // Hardcoded in production
```

### Safe

```javascript
// next.config.js
const isDevelopment = process.env.NODE_ENV !== 'production';

module.exports = {
  productionBrowserSourceMaps: isDevelopment,
  onDemandEntries: {
    maxInactiveAge: isDevelopment ? 1000 : 60000
  }
};
```

Load debug flags from `NODE_ENV`. Never hardcode `debug: true` or set
`productionBrowserSourceMaps: true` in production configuration.

## Koa debug mode

### Vulnerable

```javascript
// app.js
const Koa = require('koa');
const app = new Koa();

app.env = 'development';  // Hardcoded
app.debug = true;  // Hardcoded in production
```

### Safe

```javascript
// app.js
const Koa = require('koa');
const app = new Koa();

app.env = process.env.NODE_ENV || 'development';
app.debug = process.env.NODE_ENV !== 'production';
```

Load environment and debug flags from `NODE_ENV`. Never hardcode debug
mode in production configuration.

## Fastify debug mode

### Vulnerable

```javascript
// app.js
const fastify = require('fastify')({
  logger: {
    level: 'debug',
    prettyPrint: true  // Verbose output in production
  }
});

// or
const fastify = require('fastify')({
  logger: true  // Enables all logging levels
});
```

### Safe

```javascript
// app.js
const isDevelopment = process.env.NODE_ENV !== 'production';

const fastify = require('fastify')({
  logger: isDevelopment ? {
    level: 'debug',
    prettyPrint: true
  } : {
    level: 'error'
  }
});

// or using environment variable
const fastify = require('fastify')({
  logger: { level: process.env.LOG_LEVEL || 'info' }
});
```

Set logger level based on `NODE_ENV`. Never enable `debug` or `trace`
levels in production. Use `info` or `error` for production logging.
