# TypeScript weak PRNG patterns

Vulnerable and safe snippets for TypeScript PRNG usage the
`crypto.weak_prng` scanner recognizes.

## Math.random

### Vulnerable

```typescript
const token: string = Math.random()
  .toString(36).slice(2);

function generateOTP(): number {
  return Math.floor(Math.random() * 900000) + 100000;
}
```

### Safe

```typescript
import { randomBytes, randomUUID } from 'node:crypto';

const token: string = randomBytes(32).toString('hex');
const id: string = randomUUID();
```

Same `Math.random()` weakness as JavaScript. Use the `node:crypto`
module for security-sensitive random values.
