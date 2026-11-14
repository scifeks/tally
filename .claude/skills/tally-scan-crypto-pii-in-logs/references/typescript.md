# TypeScript PII in logs patterns

Vulnerable and safe snippets for TypeScript logging that the
`crypto.pii_in_logs` scanner recognizes.

## Structured loggers

### Vulnerable

```typescript
import { Logger } from 'winston';

logger.info('Auth', { email, password });
logger.debug('Request body', { body: req.body });
```

### Safe

```typescript
logger.info('Auth attempt', { userId: user.id });
logger.debug('Request received', {
  method: req.method,
  path: req.path,
});
```

## console.log

### Vulnerable

```typescript
console.log(`Token: ${token}`);
console.log('User:', JSON.stringify(user));
```

### Safe

```typescript
console.log(`Auth for userId: ${userId}`);
```

Same patterns as JavaScript. Use structured loggers with
redaction in production. Log identifiers, not values.
