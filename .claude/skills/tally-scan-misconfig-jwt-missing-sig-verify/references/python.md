# Python JWT signature verification patterns

Vulnerable-vs-safe snippets for PyJWT and python-jose that the
`misconfig.jwt_missing_sig_verify` scanner recognizes.

## PyJWT: disabled signature verification

### Vulnerable

```python
import jwt

payload = jwt.decode(
    token,
    options={"verify_signature": False},
)
user_id = payload["sub"]
```

```python
payload = jwt.decode(token, algorithms=["none"])
```

### Safe

```python
import jwt

payload = jwt.decode(
    token,
    key=public_key,
    algorithms=["RS256"],
)
user_id = payload["sub"]
```

Always pass the signing key and an explicit `algorithms` list.
PyJWT raises `DecodeError` when the signature is invalid.

## python-jose: disabled verification

### Vulnerable

```python
from jose import jwt

payload = jwt.decode(
    token,
    None,
    options={"verify_signature": False},
)
```

```python
payload = jwt.decode(
    token,
    None,
    algorithms=["none"],
)
```

### Safe

```python
from jose import jwt

payload = jwt.decode(
    token,
    key=public_key,
    algorithms=["RS256"],
)
```

## authlib: disabled verification

### Vulnerable

```python
from authlib.jose import jwt as authlib_jwt

claims = authlib_jwt.decode(token, None)
```

### Safe

```python
from authlib.jose import jwt as authlib_jwt

claims = authlib_jwt.decode(token, public_key)
claims.validate()
```

Call `claims.validate()` after decoding to verify expiry,
audience, and issuer claims.
