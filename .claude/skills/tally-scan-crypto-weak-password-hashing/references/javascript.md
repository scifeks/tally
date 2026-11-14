# JavaScript weak password hashing patterns

Vulnerable and safe snippets for Node.js password hashing
the `crypto.weak_password_hashing` scanner recognizes.

## crypto.createHash (fast hashes)

### Vulnerable

```javascript
const crypto = require('crypto');
const hashed = crypto.createHash('sha256')
  .update(password).digest('hex');
const hashed = crypto.createHash('md5')
  .update(password).digest('hex');
```

### Safe

```javascript
const bcrypt = require('bcrypt');
const hashed = await bcrypt.hash(password, 12);
const valid = await bcrypt.compare(input, hashed);
```

## bcrypt with low rounds

### Vulnerable

```javascript
const hashed = bcrypt.hashSync(password, 4);
```

### Safe

```javascript
const hashed = await bcrypt.hash(password, 12);
```

A salt round below 10 allows GPU-accelerated brute-force
attacks. Use 12 or higher.

## crypto.pbkdf2Sync with low iterations

### Vulnerable

```javascript
const key = crypto.pbkdf2Sync(
  password, salt, 1000, 64, 'sha256'
);
```

### Safe

```javascript
const key = crypto.pbkdf2Sync(
  password, salt, 600000, 64, 'sha256'
);
```

OWASP recommends 600000 iterations for PBKDF2-HMAC-SHA256.

## argon2 (safe reference)

```javascript
const argon2 = require('argon2');
const hashed = await argon2.hash(password);
const valid = await argon2.verify(hashed, password);
```

Argon2id is the preferred password-hashing algorithm.

## crypto.scryptSync (safe reference)

```javascript
const key = crypto.scryptSync(password, salt, 64);
```

`scrypt` is memory-hard and suitable for password hashing
with default Node.js parameters.
