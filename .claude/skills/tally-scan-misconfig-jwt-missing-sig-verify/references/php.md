# PHP JWT signature verification patterns

Vulnerable-vs-safe snippets for firebase/php-jwt and lcobucci/jwt
that the `misconfig.jwt_missing_sig_verify` scanner recognizes.

## firebase/php-jwt: missing key

### Vulnerable

```php
use Firebase\JWT\JWT;

$payload = JWT::decode($token, new Key('', 'none'));
$userId = $payload->sub;
```

### Safe

```php
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

$payload = JWT::decode(
    $token,
    new Key($publicKey, 'RS256'),
);
$userId = $payload->sub;
```

`JWT::decode()` throws `SignatureInvalidException` when the
signature does not match. Always pass a `Key` with the actual
secret or public key.

## Custom JWT parsing (manual decode)

### Vulnerable

```php
$parts = explode('.', $token);
$payload = json_decode(base64_decode($parts[1]));
$userId = $payload->sub;
```

### Safe

```php
use Firebase\JWT\JWT;
use Firebase\JWT\Key;

$payload = JWT::decode(
    $token,
    new Key($publicKey, 'RS256'),
);
$userId = $payload->sub;
```

Manual base64 decoding skips signature verification entirely.
Use a maintained JWT library.

## lcobucci/jwt: missing verification step

### Vulnerable

```php
use Lcobucci\JWT\Encoding\JoseEncoder;
use Lcobucci\JWT\Token\Parser;

$parser = new Parser(new JoseEncoder());
$token = $parser->parse($tokenString);
$userId = $token->claims()->get('sub');
```

### Safe

```php
use Lcobucci\JWT\Configuration;
use Lcobucci\JWT\Signer\Rsa\Sha256;
use Lcobucci\JWT\Signer\Key\InMemory;

$config = Configuration::forAsymmetricSigner(
    new Sha256(),
    InMemory::plainText($privateKey),
    InMemory::plainText($publicKey),
);
$token = $config->parser()->parse($tokenString);
$constraints = $config->validationConstraints();
$config->validator()->assert($token, ...$constraints);
$userId = $token->claims()->get('sub');
```

Parsing and verification are separate steps in lcobucci/jwt.
Always call `validator()->assert()` before reading claims.
