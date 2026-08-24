# TypeScript JWT algorithm confusion patterns

Vulnerable-vs-safe snippets for typed jsonwebtoken and jose that
the `misconfig.jwt_alg_confusion` scanner recognizes.
JavaScript patterns from `javascript.md` apply at runtime.

## jsonwebtoken: missing algorithms (typed)

### Vulnerable

```typescript
import jwt, { JwtPayload } from "jsonwebtoken";

const payload = jwt.verify(
  token,
  publicKey,
) as JwtPayload;
```

### Safe

```typescript
import jwt, { JwtPayload } from "jsonwebtoken";

const payload = jwt.verify(token, publicKey, {
  algorithms: ["RS256"],
}) as JwtPayload;
```

`VerifyOptions.algorithms` is typed as `Algorithm[] | undefined`.
The `undefined` default compiles cleanly but accepts any
algorithm at runtime.

## jose: missing algorithms (typed)

### Vulnerable

```typescript
import { jwtVerify, JWTPayload } from "jose";

const { payload } = await jwtVerify(token, publicKey);
```

### Safe

```typescript
import { jwtVerify, JWTPayload } from "jose";

const { payload } = await jwtVerify(token, publicKey, {
  algorithms: ["RS256"],
});
```

TypeScript types do not enforce algorithm restriction at
compile time. Add explicit `algorithms` for runtime safety.
