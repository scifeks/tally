# JavaScript JWT algorithm confusion patterns

Vulnerable-vs-safe snippets for jsonwebtoken and jose that the
`misconfig.jwt_alg_confusion` scanner recognizes.

## jsonwebtoken: missing algorithms option

### Vulnerable

```javascript
const jwt = require("jsonwebtoken");

const payload = jwt.verify(token, publicKey);
```

### Safe

```javascript
const jwt = require("jsonwebtoken");

const payload = jwt.verify(token, publicKey, {
  algorithms: ["RS256"],
});
```

Without the `algorithms` option, the library accepts the
algorithm declared in the token header.

## jsonwebtoken: algorithm from token header

### Vulnerable

```javascript
const decoded = jwt.decode(token, { complete: true });
const alg = decoded.header.alg;
const key = alg.startsWith("HS") ? hmacSecret : rsaPublicKey;
const payload = jwt.verify(token, key, {
  algorithms: [alg],
});
```

### Safe

```javascript
const payload = jwt.verify(token, rsaPublicKey, {
  algorithms: ["RS256"],
});
```

The algorithm must come from the server configuration, not
from the token.

## jose: missing algorithms option

### Vulnerable

```javascript
const { jwtVerify } = require("jose");

const { payload } = await jwtVerify(token, publicKey);
```

### Safe

```javascript
const { jwtVerify } = require("jose");

const { payload } = await jwtVerify(token, publicKey, {
  algorithms: ["RS256"],
});
```

The `jose` library restricts by key type by default, but
explicit restriction prevents regressions if the key type
changes.
