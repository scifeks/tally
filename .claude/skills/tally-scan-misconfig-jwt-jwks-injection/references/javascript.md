# JavaScript JWKS injection patterns

Vulnerable-vs-safe snippets for jose and jsonwebtoken that the
`misconfig.jwt_jwks_injection` scanner recognizes.

## jose: createRemoteJWKSet with token URL

### Vulnerable

```javascript
const {
  decodeProtectedHeader,
  createRemoteJWKSet,
  jwtVerify,
} = require("jose");

const header = decodeProtectedHeader(token);
const JWKS = createRemoteJWKSet(new URL(header.jku));
const { payload } = await jwtVerify(token, JWKS, {
  algorithms: ["RS256"],
});
```

### Safe

```javascript
const { createRemoteJWKSet, jwtVerify } = require("jose");

const JWKS_URL = process.env.JWKS_URL;
const JWKS = createRemoteJWKSet(new URL(JWKS_URL));
const { payload } = await jwtVerify(token, JWKS, {
  algorithms: ["RS256"],
});
```

Hardcode or load the JWKS URL from server configuration.
`createRemoteJWKSet` caches the fetched keys and selects by
`kid` automatically.

## jose: embedded JWK import

### Vulnerable

```javascript
const {
  decodeProtectedHeader,
  importJWK,
  jwtVerify,
} = require("jose");

const header = decodeProtectedHeader(token);
const key = await importJWK(header.jwk, "RS256");
const { payload } = await jwtVerify(token, key, {
  algorithms: ["RS256"],
});
```

### Safe

```javascript
const { importSPKI, jwtVerify } = require("jose");

const publicKey = await importSPKI(
  process.env.JWT_PUBLIC_KEY,
  "RS256",
);
const { payload } = await jwtVerify(token, publicKey, {
  algorithms: ["RS256"],
});
```

Import the public key from a server-side source. Never call
`importJWK` with data from the token header.

## jsonwebtoken: key from token header

### Vulnerable

```javascript
const jwt = require("jsonwebtoken");

const decoded = jwt.decode(token, { complete: true });
const key = fetchKey(decoded.header.jku, decoded.header.kid);
const payload = jwt.verify(token, key, {
  algorithms: ["RS256"],
});
```

### Safe

```javascript
const jwt = require("jsonwebtoken");
const jwksClient = require("jwks-rsa");

const client = jwksClient({
  jwksUri: process.env.JWKS_URL,
});

function getKey(header, callback) {
  client.getSigningKey(header.kid, (err, key) => {
    callback(null, key.getPublicKey());
  });
}

jwt.verify(token, getKey, { algorithms: ["RS256"] });
```

The `jwks-rsa` library fetches keys from a pinned URL. The
`kid` from the header selects a key from the pinned set; this
is safe because the key source is server-controlled.
