# PHP weak cryptographic algorithm patterns

Vulnerable and safe snippets for the PHP crypto functions the
`crypto.weak_algorithm` scanner recognizes.

## mcrypt extension (removed in PHP 7.2+)

### Vulnerable

```php
$ciphertext = mcrypt_encrypt(
    MCRYPT_DES,
    $key,
    $plaintext,
    MCRYPT_MODE_ECB
);

$ciphertext = mcrypt_encrypt(
    MCRYPT_3DES,
    $key,
    $plaintext,
    MCRYPT_MODE_CBC,
    $iv
);
```

### Safe

```php
$iv = openssl_random_pseudo_bytes(
    openssl_cipher_iv_length('aes-256-gcm')
);
$ciphertext = openssl_encrypt(
    $plaintext,
    'aes-256-gcm',
    $key,
    OPENSSL_RAW_DATA,
    $iv,
    $tag
);
```

The mcrypt extension is removed in PHP 7.2+. Use
`openssl_encrypt` with `aes-256-gcm` or the Sodium
extension (`sodium_crypto_secretbox`).

## OpenSSL: weak ciphers

### Vulnerable

```php
$ct = openssl_encrypt($data, 'des-ecb', $key);
$ct = openssl_encrypt($data, 'rc4', $key);
$ct = openssl_encrypt($data, 'bf-cbc', $key, 0, $iv);
```

### Safe

```php
$ct = openssl_encrypt(
    $data,
    'aes-256-gcm',
    $key,
    OPENSSL_RAW_DATA,
    $iv,
    $tag
);
```

## OpenSSL: ECB mode

### Vulnerable

```php
$ct = openssl_encrypt(
    $data, 'aes-128-ecb', $key
);
```

### Safe

```php
$ct = openssl_encrypt(
    $data,
    'aes-256-gcm',
    $key,
    OPENSSL_RAW_DATA,
    $iv,
    $tag
);
```

ECB mode leaks plaintext patterns. Use GCM for
authenticated encryption or CBC with a random IV.

## MD5/SHA1 for integrity

### Vulnerable

```php
$token = md5($session_data);
$signature = sha1($message . $secret);
```

### Safe

```php
$token = hash('sha256', $session_data);
$signature = hash_hmac('sha256', $message, $secret);
```

Use `hash_hmac` for keyed integrity checks to prevent
length-extension attacks.

## RSA key size

### Vulnerable

```php
$key = openssl_pkey_new([
    'private_key_bits' => 1024,
    'private_key_type' => OPENSSL_KEYTYPE_RSA,
]);
```

### Safe

```php
$key = openssl_pkey_new([
    'private_key_bits' => 4096,
    'private_key_type' => OPENSSL_KEYTYPE_RSA,
]);
```

## Sodium (safe reference)

```php
$nonce = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
$ct = sodium_crypto_secretbox($data, $nonce, $key);
```

Sodium's `secretbox` uses XSalsa20-Poly1305 and is the
recommended symmetric encryption API in modern PHP.
