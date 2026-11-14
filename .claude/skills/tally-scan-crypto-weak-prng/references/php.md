# PHP weak PRNG patterns

Vulnerable and safe snippets for PHP PRNG usage the `crypto.weak_prng`
scanner recognizes.

## rand / mt_rand

### Vulnerable

```php
$token = '';
for ($i = 0; $i < 32; $i++) {
    $token .= dechex(mt_rand(0, 15));
}
$otp = rand(100000, 999999);
```

### Safe

```php
$token = bin2hex(random_bytes(32));
$otp = random_int(100000, 999999);
```

`mt_rand` uses Mersenne Twister. After observing 624 outputs, the full
internal state is recoverable. `random_bytes` and `random_int` use the
OS CSPRNG.

## uniqid

### Vulnerable

```php
$token = uniqid('', true);
$resetToken = uniqid('reset_');
```

### Safe

```php
$token = bin2hex(random_bytes(32));
```

`uniqid` is time-based and trivially predictable. It produces at most
23 hex characters of entropy derived from `gettimeofday`.

## array_rand / shuffle

### Vulnerable

```php
$chars = str_split('abcdef0123456789');
$token = '';
for ($i = 0; $i < 32; $i++) {
    $token .= $chars[array_rand($chars)];
}
```

### Safe

```php
$token = bin2hex(random_bytes(32));
```

`array_rand` uses the non-cryptographic internal PRNG.
