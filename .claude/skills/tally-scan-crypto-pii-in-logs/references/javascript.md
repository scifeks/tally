# JavaScript PII in logs patterns

Vulnerable and safe snippets for Node.js logging that the
`crypto.pii_in_logs` scanner recognizes.

## console.log

### Vulnerable

```javascript
console.log('Token:', token);
console.log('User:', user);
console.log('Password:', password);
```

### Safe

```javascript
console.log('Auth attempt for userId:', userId);
```

`console.log` in production code is a code smell. Use a
structured logger with redaction support.

## Structured loggers (winston, pino)

### Vulnerable

```javascript
logger.info({ body: req.body });
logger.info({ user });
logger.error('Auth failed', { password, token });
```

### Safe

```javascript
logger.info({
  method: req.method,
  path: req.path,
  requestId: req.id,
});
logger.error('Auth failed', { userId });
```

## Pino redaction (safe reference)

```javascript
const pino = require('pino');
const logger = pino({
  redact: [
    'req.headers.authorization',
    'req.body.password',
    'req.body.token',
    'req.body.creditCard',
  ],
});
```

Configure field-level redaction on the logger itself as a
defense-in-depth measure.
