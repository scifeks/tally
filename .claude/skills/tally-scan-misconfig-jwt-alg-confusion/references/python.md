# Python JWT algorithm confusion patterns

Vulnerable-vs-safe snippets for PyJWT and python-jose that the
`misconfig.jwt_alg_confusion` scanner recognizes.

## PyJWT: mixed algorithm families

### Vulnerable

```python
import jwt

payload = jwt.decode(
    token,
    public_key,
    algorithms=["HS256", "RS256"],
)
```

### Safe

```python
import jwt

payload = jwt.decode(
    token,
    public_key,
    algorithms=["RS256"],
)
```

When both HS256 and RS256 are accepted, an attacker can create
a token signed with HS256 using the RSA public key (which is
often publicly available) as the HMAC secret. The server
verifies the HMAC signature against the public key and accepts
the forged token.

## PyJWT: missing algorithms parameter

### Vulnerable

```python
payload = jwt.decode(token, key)
```

### Safe

```python
payload = jwt.decode(
    token,
    key,
    algorithms=["RS256"],
)
```

Current PyJWT versions require `algorithms`, but legacy code
may use older versions that accept any algorithm by default.

## python-jose: mixed algorithms

### Vulnerable

```python
from jose import jwt

payload = jwt.decode(
    token,
    key,
    algorithms=["HS256", "RS256", "ES256"],
)
```

### Safe

```python
from jose import jwt

payload = jwt.decode(
    token,
    key,
    algorithms=["RS256"],
)
```

Restrict to a single algorithm family. If the application uses
RSA, accept only RS256 (or RS384/RS512).
