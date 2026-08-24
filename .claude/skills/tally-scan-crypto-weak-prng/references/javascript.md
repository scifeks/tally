# JavaScript weak PRNG patterns

Vulnerable and safe snippets for JavaScript PRNG usage the
`crypto.weak_prng` scanner recognizes.

## Math.random

### Vulnerable

```javascript
const token = Math.random().toString(36).slice(2);

function generateOTP() {
  return Math.floor(Math.random() * 900000) + 100000;
}

const sessionId = Array.from(
  { length: 32 },
  () => Math.floor(Math.random() * 16).toString(16)
).join('');
```

### Safe

```javascript
const crypto = require('crypto');
const token = crypto.randomBytes(32).toString('hex');

function generateOTP() {
  return crypto.randomInt(100000, 999999);
}

const sessionId = crypto.randomUUID();
```

`Math.random()` is not cryptographically secure on any JavaScript
engine. Its output is predictable.

## Browser context (safe reference)

```javascript
const array = new Uint8Array(32);
crypto.getRandomValues(array);
const token = Array.from(
  array, b => b.toString(16).padStart(2, '0')
).join('');
```

In browser contexts, use `crypto.getRandomValues()` from the Web
Crypto API.
