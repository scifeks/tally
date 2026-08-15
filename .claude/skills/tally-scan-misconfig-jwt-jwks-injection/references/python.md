# Python JWKS injection patterns

Vulnerable-vs-safe snippets for PyJWKClient and authlib that the
`misconfig.jwt_jwks_injection` scanner recognizes.

## PyJWKClient: URL from token header

### Vulnerable

```python
import jwt
from jwt import PyJWKClient

header = jwt.get_unverified_header(token)
jwks_client = PyJWKClient(header["jku"])
signing_key = jwks_client.get_signing_key_from_jwt(token)
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256"],
)
```

### Safe

```python
import jwt
from jwt import PyJWKClient

JWKS_URL = "https://auth.example.com/.well-known/jwks.json"
jwks_client = PyJWKClient(JWKS_URL)
signing_key = jwks_client.get_signing_key_from_jwt(token)
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256"],
)
```

The JWKS URL must be a constant or loaded from server
configuration. `get_signing_key_from_jwt()` reads the `kid`
from the token header to select a key from the fetched set;
this is safe because the key itself comes from the pinned URL.

## Embedded JWK from token header

### Vulnerable

```python
import jwt
from jwt.algorithms import RSAAlgorithm

header = jwt.get_unverified_header(token)
public_key = RSAAlgorithm.from_jwk(header["jwk"])
payload = jwt.decode(
    token,
    public_key,
    algorithms=["RS256"],
)
```

### Safe

```python
import jwt
from jwt import PyJWKClient

JWKS_URL = os.environ["JWKS_URL"]
jwks_client = PyJWKClient(JWKS_URL)
signing_key = jwks_client.get_signing_key_from_jwt(token)
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["RS256"],
)
```

Never construct a verification key from the token's embedded
`jwk` claim. An attacker can embed their own public key and
sign the token with the matching private key.
