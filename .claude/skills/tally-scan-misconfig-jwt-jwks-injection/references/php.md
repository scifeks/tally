# PHP JWKS injection patterns

Vulnerable-vs-safe snippets for PHP JWT key handling that the
`misconfig.jwt_jwks_injection` scanner recognizes.

## JWKS URL from token header

### Vulnerable

```php
$header = json_decode(
    base64_decode(explode('.', $token)[0]),
);
$jwksUrl = $header->jku;
$jwks = json_decode(
    file_get_contents($jwksUrl),
);
$key = $jwks->keys[0];
$payload = JWT::decode(
    $token,
    new Key(jwkToPem($key), 'RS256'),
);
```

### Safe

```php
$jwksUrl = env('JWKS_URL');
$jwks = json_decode(
    file_get_contents($jwksUrl),
);
$key = findKeyByKid($jwks, $kid);
$payload = JWT::decode(
    $token,
    new Key(jwkToPem($key), 'RS256'),
);
```

Pin the JWKS URL in environment or configuration. Use the `kid`
from the token header only to select a key from the pinned
endpoint's response.

## Embedded JWK from token

### Vulnerable

```php
$header = json_decode(
    base64_decode(explode('.', $token)[0]),
);
$embeddedKey = $header->jwk;
$pem = jwkToPem($embeddedKey);
$payload = JWT::decode(
    $token,
    new Key($pem, 'RS256'),
);
```

### Safe

```php
$publicKey = file_get_contents(
    config('jwt.public_key_path'),
);
$payload = JWT::decode(
    $token,
    new Key($publicKey, 'RS256'),
);
```

Load the verification key from a trusted source (file, config,
secrets manager), not from the token.

## x5u certificate URL

### Vulnerable

```php
$header = json_decode(
    base64_decode(explode('.', $token)[0]),
);
$certUrl = $header->x5u;
$cert = file_get_contents($certUrl);
$publicKey = openssl_pkey_get_public($cert);
```

### Safe

```php
$certUrl = env('JWT_CERT_URL');
$cert = file_get_contents($certUrl);
$publicKey = openssl_pkey_get_public($cert);
```

The `x5u` header points to an X.509 certificate chain. An
attacker can host their own certificate at an arbitrary URL.
Pin the certificate URL in server configuration.
