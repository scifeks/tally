# TypeScript JWKS injection patterns

Vulnerable-vs-safe snippets for typed jose that the
`misconfig.jwt_jwks_injection` scanner recognizes. JavaScript
patterns from `javascript.md` apply at runtime.

## jose: createRemoteJWKSet with token URL (typed)

### Vulnerable

```typescript
import {
  decodeProtectedHeader,
  createRemoteJWKSet,
  jwtVerify,
} from "jose";

const header = decodeProtectedHeader(token);
const JWKS = createRemoteJWKSet(
  new URL(header.jku as string),
);
const { payload } = await jwtVerify(token, JWKS, {
  algorithms: ["RS256"],
});
```

### Safe

```typescript
import { createRemoteJWKSet, jwtVerify } from "jose";

const JWKS_URL = process.env.JWKS_URL!;
const JWKS = createRemoteJWKSet(new URL(JWKS_URL));
const { payload } = await jwtVerify(token, JWKS, {
  algorithms: ["RS256"],
});
```

The `as string` cast on `header.jku` is a red flag. The URL
must come from server configuration, not from the token.

## jose: embedded JWK import (typed)

### Vulnerable

```typescript
import {
  decodeProtectedHeader,
  importJWK,
  jwtVerify,
  JWK,
} from "jose";

const header = decodeProtectedHeader(token);
const key = await importJWK(header.jwk as JWK, "RS256");
const { payload } = await jwtVerify(token, key, {
  algorithms: ["RS256"],
});
```

### Safe

```typescript
import { importSPKI, jwtVerify } from "jose";

const publicKey = await importSPKI(
  process.env.JWT_PUBLIC_KEY!,
  "RS256",
);
const { payload } = await jwtVerify(token, publicKey, {
  algorithms: ["RS256"],
});
```

TypeScript types do not prevent importing keys from untrusted
sources. The `as JWK` cast compiles but creates a forgery path.
