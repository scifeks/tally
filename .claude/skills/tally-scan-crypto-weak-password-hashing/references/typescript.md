# TypeScript weak password hashing patterns

Vulnerable and safe snippets for Node.js password hashing
in TypeScript the `crypto.weak_password_hashing` scanner
recognizes.

## crypto.createHash (fast hashes)

### Vulnerable

```typescript
import { createHash } from 'node:crypto';

const hashed: string = createHash('sha256')
  .update(password)
  .digest('hex');
```

### Safe

```typescript
import bcrypt from 'bcrypt';

const hashed: string = await bcrypt.hash(password, 12);
const valid: boolean = await bcrypt.compare(
  input, hashed
);
```

## bcrypt with low rounds

### Vulnerable

```typescript
import bcrypt from 'bcrypt';

const hashed: string = bcrypt.hashSync(password, 4);
```

### Safe

```typescript
const hashed: string = await bcrypt.hash(password, 12);
```

## argon2 (safe reference)

```typescript
import argon2 from 'argon2';

const hashed: string = await argon2.hash(password);
const valid: boolean = await argon2.verify(
  hashed, password
);
```

Same Node.js password hashing sinks as JavaScript apply.
Prefer Argon2id for new systems.
