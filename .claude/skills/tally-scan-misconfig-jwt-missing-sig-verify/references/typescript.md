# TypeScript JWT signature verification patterns

Vulnerable-vs-safe snippets for typed jsonwebtoken and jose that
the `misconfig.jwt_missing_sig_verify` scanner recognizes.
JavaScript patterns from `javascript.md` apply at runtime.

## jsonwebtoken: decode (typed)

### Vulnerable

```typescript
import jwt, { JwtPayload } from "jsonwebtoken";

const payload = jwt.decode(token) as JwtPayload;
const userId = payload.sub;
```

### Safe

```typescript
import jwt, { JwtPayload } from "jsonwebtoken";

const payload = jwt.verify(token, process.env.JWT_SECRET!, {
  algorithms: ["HS256"],
}) as JwtPayload;
const userId = payload.sub;
```

The `as JwtPayload` cast does not add safety. The signature
must be verified by calling `verify()`, not `decode()`.

## jose: decodeJwt (typed)

### Vulnerable

```typescript
import { decodeJwt, JWTPayload } from "jose";

const payload: JWTPayload = decodeJwt(token);
const userId = payload.sub;
```

### Safe

```typescript
import { jwtVerify, JWTPayload } from "jose";

const { payload } = await jwtVerify(
  token,
  publicKey,
  { algorithms: ["RS256"] },
);
const userId = payload.sub;
```

TypeScript's type system does not distinguish verified from
unverified payloads. Use `jwtVerify()` for any claim that
influences access control.
