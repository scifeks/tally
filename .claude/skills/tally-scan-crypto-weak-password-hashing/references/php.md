# PHP weak password hashing patterns

Vulnerable and safe snippets for PHP password hashing
functions the `crypto.weak_password_hashing` scanner
recognizes.

## md5 / sha1 / hash

### Vulnerable

```php
$hashed = md5($password);
$hashed = sha1($password);
$hashed = hash('sha256', $password);
$hashed = hash('sha256', $salt . $password);
```

### Safe

```php
$hashed = password_hash(
    $password, PASSWORD_ARGON2ID
);
$valid = password_verify($password, $hashed);
```

`password_hash` with `PASSWORD_ARGON2ID` is the recommended
approach. It handles salt generation and parameter tuning.

## crypt

### Vulnerable

```php
$hashed = crypt($password, '$1$mysalt$');
$hashed = crypt($password, 'ab');
```

### Safe

```php
$hashed = password_hash(
    $password, PASSWORD_BCRYPT
);
```

`crypt` with `$1$` uses MD5, and DES-based crypt uses a
two-character salt. Both are broken. Use `password_hash`
instead of calling `crypt` directly.

## password_hash with low cost

### Vulnerable

```php
$hashed = password_hash(
    $password,
    PASSWORD_BCRYPT,
    ['cost' => 4]
);
```

### Safe

```php
$hashed = password_hash(
    $password,
    PASSWORD_BCRYPT,
    ['cost' => 12]
);

$hashed = password_hash(
    $password, PASSWORD_ARGON2ID
);
```

PHP's default bcrypt cost is 10. For new systems, use
`PASSWORD_ARGON2ID` with PHP's defaults. The minimum
acceptable bcrypt cost is 10.
