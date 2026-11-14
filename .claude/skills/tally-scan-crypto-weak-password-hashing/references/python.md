# Python weak password hashing patterns

Vulnerable and safe snippets for Python password hashing
libraries the `crypto.weak_password_hashing` scanner
recognizes.

## hashlib (fast hashes)

### Vulnerable

```python
import hashlib

hashed = hashlib.md5(password.encode()).hexdigest()
hashed = hashlib.sha1(password.encode()).hexdigest()
hashed = hashlib.sha256(
    (salt + password).encode()
).hexdigest()
```

### Safe

```python
import bcrypt

hashed = bcrypt.hashpw(
    password.encode(), bcrypt.gensalt(rounds=12)
)
```

MD5, SHA1, and SHA256 are not password-hashing functions.
They are fast hashes designed for data integrity. Password
hashing requires a slow, memory-hard key derivation function.

## bcrypt

### Vulnerable

```python
import bcrypt

hashed = bcrypt.hashpw(
    password.encode(), bcrypt.gensalt(rounds=4)
)
```

### Safe

```python
hashed = bcrypt.hashpw(
    password.encode(), bcrypt.gensalt(rounds=12)
)
```

A cost factor below 10 allows brute-force attacks on modern
GPUs. Use 12 or higher for production systems.

## argon2-cffi

### Safe

```python
from argon2 import PasswordHasher

ph = PasswordHasher()
hashed = ph.hash(password)
is_valid = ph.verify(hashed, password)
```

Argon2id is the recommended password-hashing algorithm per
OWASP. The `argon2-cffi` library uses safe defaults.

## hashlib.pbkdf2_hmac

### Vulnerable

```python
import hashlib

hashed = hashlib.pbkdf2_hmac(
    'sha256', password.encode(), salt, 1000
)
```

### Safe

```python
hashed = hashlib.pbkdf2_hmac(
    'sha256', password.encode(), salt, 600000
)
```

OWASP recommends at least 600000 iterations for
PBKDF2-HMAC-SHA256.

## hashlib.scrypt

### Safe

```python
import hashlib

hashed = hashlib.scrypt(
    password.encode(),
    salt=salt,
    n=16384,
    r=8,
    p=1,
)
```

`scrypt` is memory-hard. Use n=16384, r=8, p=1 as the
minimum parameters.
