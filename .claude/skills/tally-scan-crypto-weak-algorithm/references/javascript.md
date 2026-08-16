# JavaScript weak cryptographic algorithm patterns

Vulnerable and safe snippets for the Node.js `crypto` module
the `crypto.weak_algorithm` scanner recognizes.

## Deprecated createCipher

### Vulnerable

```javascript
const crypto = require('crypto');
const cipher = crypto.createCipher('des', password);
let ct = cipher.update(data, 'utf8', 'hex');
ct += cipher.final('hex');
```

### Safe

```javascript
const crypto = require('crypto');
const key = crypto.randomBytes(32);
const iv = crypto.randomBytes(12);
const cipher = crypto.createCipheriv(
  'aes-256-gcm', key, iv
);
let ct = cipher.update(data, 'utf8', 'hex');
ct += cipher.final('hex');
const tag = cipher.getAuthTag();
```

`createCipher` is deprecated. It uses a weak key derivation
(single MD5 round). Always use `createCipheriv` with AES-GCM.

## Weak algorithms in createCipheriv

### Vulnerable

```javascript
const cipher = crypto.createCipheriv('des-ecb', key, '');
const cipher = crypto.createCipheriv('rc4', key, '');
const cipher = crypto.createCipheriv(
  'bf-cbc', key, iv
);
```

### Safe

```javascript
const cipher = crypto.createCipheriv(
  'aes-256-gcm', key, iv
);
```

## ECB mode

### Vulnerable

```javascript
const cipher = crypto.createCipheriv(
  'aes-128-ecb', key, ''
);
```

### Safe

```javascript
const cipher = crypto.createCipheriv(
  'aes-256-gcm', key, iv
);
```

## MD5/SHA1 for integrity

### Vulnerable

```javascript
const token = crypto.createHash('md5')
  .update(sessionData).digest('hex');
const sig = crypto.createHash('sha1')
  .update(message + secret).digest('hex');
```

### Safe

```javascript
const token = crypto.createHash('sha256')
  .update(sessionData).digest('hex');
const sig = crypto.createHmac('sha256', secret)
  .update(message).digest('hex');
```

Use `createHmac` for keyed integrity rather than hash
concatenation.

## RSA key size

### Vulnerable

```javascript
const { publicKey, privateKey } =
  crypto.generateKeyPairSync('rsa', {
    modulusLength: 1024,
  });
```

### Safe

```javascript
const { publicKey, privateKey } =
  crypto.generateKeyPairSync('rsa', {
    modulusLength: 4096,
  });
```

Use 2048 bits minimum, 4096 for long-lived keys.
