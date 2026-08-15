# Python weak cryptographic algorithm patterns

Vulnerable and safe snippets for the Python crypto libraries
the `crypto.weak_algorithm` scanner recognizes.

## PyCryptodome: block ciphers

### Vulnerable

```python
from Crypto.Cipher import DES

key = b"8bytekey"
cipher = DES.new(key, DES.MODE_ECB)
ciphertext = cipher.encrypt(pad(data, DES.block_size))
```

```python
from Crypto.Cipher import ARC4

cipher = ARC4.new(key)
ciphertext = cipher.encrypt(data)
```

### Safe

```python
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes

key = get_random_bytes(32)
cipher = AES.new(key, AES.MODE_GCM)
ciphertext, tag = cipher.encrypt_and_digest(data)
```

AES-256-GCM provides authenticated encryption. Store the
nonce (`cipher.nonce`) and tag alongside the ciphertext.

## PyCryptodome: ECB mode

### Vulnerable

```python
from Crypto.Cipher import AES

cipher = AES.new(key, AES.MODE_ECB)
ciphertext = cipher.encrypt(pad(data, AES.block_size))
```

### Safe

```python
cipher = AES.new(key, AES.MODE_GCM)
ciphertext, tag = cipher.encrypt_and_digest(data)
```

ECB encrypts each block independently, leaking patterns in
the plaintext. GCM or CBC with a random IV avoids this.

## cryptography library

### Vulnerable

```python
from cryptography.hazmat.primitives.ciphers import (
    Cipher, algorithms, modes,
)

cipher = Cipher(algorithms.TripleDES(key), modes.CBC(iv))
encryptor = cipher.encryptor()
ct = encryptor.update(data) + encryptor.finalize()
```

### Safe

```python
from cryptography.hazmat.primitives.ciphers.aead import (
    AESGCM,
)

aesgcm = AESGCM(key)
ct = aesgcm.encrypt(nonce, data, associated_data)
```

The `cryptography` library's AEAD interface (AESGCM,
ChaCha20Poly1305) is the preferred high-level API.

## hashlib for integrity

### Vulnerable

```python
import hashlib

token = hashlib.md5(session_data.encode()).hexdigest()
signature = hashlib.sha1(
    (message + secret).encode()
).hexdigest()
```

### Safe

```python
import hashlib
import hmac

token = hashlib.sha256(
    session_data.encode()
).hexdigest()
signature = hmac.new(
    secret.encode(), message.encode(), hashlib.sha256
).hexdigest()
```

For HMAC use cases, use the `hmac` module rather than raw
hash concatenation to prevent length-extension attacks.

## RSA key size

### Vulnerable

```python
from cryptography.hazmat.primitives.asymmetric import rsa

private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=1024,
)
```

### Safe

```python
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=4096,
)
```

Use 2048 bits minimum, 4096 for long-lived keys. For new
systems, prefer Ed25519 signatures or X25519 key exchange.
