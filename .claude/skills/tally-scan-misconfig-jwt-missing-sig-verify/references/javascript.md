# JavaScript JWT signature verification patterns

Vulnerable-vs-safe snippets for jsonwebtoken and jose that the
`misconfig.jwt_missing_sig_verify` scanner recognizes.

## jsonwebtoken: decode vs verify

### Vulnerable

```javascript
const jwt = require("jsonwebtoken");

const payload = jwt.decode(token);
const userId = payload.sub;
```

### Safe

```javascript
const jwt = require("jsonwebtoken");

const payload = jwt.verify(token, process.env.JWT_SECRET, {
  algorithms: ["HS256"],
});
const userId = payload.sub;
```

`jwt.decode()` only base64-decodes the payload. It does not
verify the signature. Use `jwt.verify()` for access-control
decisions.

## jose: decodeJwt vs jwtVerify

### Vulnerable

```javascript
const { decodeJwt } = require("jose");

const payload = decodeJwt(token);
const userId = payload.sub;
```

### Safe

```javascript
const { jwtVerify } = require("jose");

const { payload } = await jwtVerify(
  token,
  publicKey,
  { algorithms: ["RS256"] },
);
const userId = payload.sub;
```

`decodeJwt()` returns the payload without verification.
`jwtVerify()` validates the signature and returns the payload
only on success.

## jose: header inspection before verification

### Vulnerable (stops at header)

```javascript
const { decodeProtectedHeader } = require("jose");

const header = decodeProtectedHeader(token);
if (header.alg === "RS256") {
  // trusts token without verification
  const payload = decodeJwt(token);
}
```

### Safe

```javascript
const {
  decodeProtectedHeader,
  jwtVerify,
} = require("jose");

const header = decodeProtectedHeader(token);
const key = await getKeyByKid(header.kid);
const { payload } = await jwtVerify(token, key, {
  algorithms: ["RS256"],
});
```

Reading the header to select a key is safe only when followed
by `jwtVerify()` with that key.
