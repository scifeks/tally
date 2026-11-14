# PHP JWT algorithm confusion patterns

Vulnerable-vs-safe snippets for firebase/php-jwt that the
`misconfig.jwt_alg_confusion` scanner recognizes.

## firebase/php-jwt: mixed key types

### Vulnerable

```php
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

$keys = [
    'rsa-kid' => new Key($rsaPublicKey, 'RS256'),
    'hmac-kid' => new Key($hmacSecret, 'HS256'),
];
$payload = JWT::decode($token, $keys);
```

### Safe

```php
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

$payload = JWT::decode(
    $token,
    new Key($rsaPublicKey, 'RS256'),
);
```

Use a single Key object with one algorithm. If multiple key IDs
are needed (key rotation), all keys must use the same algorithm
family.

## Algorithm from token header

### Vulnerable

```php
$header = json_decode(
    base64_decode(explode('.', $token)[0]),
);
$alg = $header->alg;
$payload = JWT::decode(
    $token,
    new Key($key, $alg),
);
```

### Safe

```php
$payload = JWT::decode(
    $token,
    new Key($rsaPublicKey, 'RS256'),
);
```

The algorithm must be server-configured. Never read it from
the token header.
