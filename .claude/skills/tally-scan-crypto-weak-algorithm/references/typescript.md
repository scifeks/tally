# TypeScript weak cryptographic algorithm patterns

Vulnerable and safe snippets for Node.js `crypto` in
TypeScript. The `crypto.weak_algorithm` scanner recognizes
the same sinks as JavaScript with typed imports.

## Weak ciphers via node:crypto

### Vulnerable

```typescript
import { createCipheriv } from 'node:crypto';

const cipher = createCipheriv('des-ecb', key, '');
const ct = Buffer.concat([
  cipher.update(data),
  cipher.final(),
]);
```

### Safe

```typescript
import {
  createCipheriv,
  randomBytes,
} from 'node:crypto';

const key = randomBytes(32);
const iv = randomBytes(12);
const cipher = createCipheriv('aes-256-gcm', key, iv);
const ct = Buffer.concat([
  cipher.update(data),
  cipher.final(),
]);
const tag = cipher.getAuthTag();
```

## MD5/SHA1 for integrity

### Vulnerable

```typescript
import { createHash } from 'node:crypto';

const token: string = createHash('md5')
  .update(sessionData)
  .digest('hex');
```

### Safe

```typescript
import { createHash, createHmac } from 'node:crypto';

const token: string = createHash('sha256')
  .update(sessionData)
  .digest('hex');
const sig: string = createHmac('sha256', secret)
  .update(message)
  .digest('hex');
```

## RSA key size

### Vulnerable

```typescript
import { generateKeyPairSync } from 'node:crypto';

const { publicKey, privateKey } =
  generateKeyPairSync('rsa', {
    modulusLength: 1024,
  });
```

### Safe

```typescript
const { publicKey, privateKey } =
  generateKeyPairSync('rsa', {
    modulusLength: 4096,
  });
```

Same Node.js `crypto` module patterns as JavaScript. The
typed import from `node:crypto` does not change the
underlying algorithm behavior.
