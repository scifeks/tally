"""Per-project credential encryption using passphrase-derived Fernet keys."""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class BrokenEncryptionKey(RuntimeError):
    """The credentials key is missing or broken."""


_KDF_ITERATIONS = 600_000
_SALT_BYTES = 16
_KEY_VERSION = 1


def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from a passphrase and salt."""
    kdf = PBKDF2HMAC(
        algorithm=SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def create_key_file(passphrase: str, key_path: Path) -> bytes:
    """Derive a Fernet key from *passphrase* and write it to *key_path*.

    Returns the derived key bytes.
    """
    salt = os.urandom(_SALT_BYTES)
    key = _derive_fernet_key(passphrase, salt)
    key_data = json.dumps(
        {
            "version": _KEY_VERSION,
            "salt": salt.hex(),
            "key": key.decode(),
        }
    )
    key_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        str(key_path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(fd, "w") as f:
        f.write(key_data)
    return key


def load_key(key_path: Path) -> bytes:
    """Load a Fernet key from a key file."""
    data = json.loads(key_path.read_text())
    return data["key"].encode()


def validate_fernet_key(key: bytes) -> None:
    """Raise ValueError if *key* is not a valid Fernet key."""
    try:
        Fernet(key)
    except Exception as exc:
        raise ValueError(f"Invalid Fernet key: {exc}") from exc


def get_encryption_key(key_path: Path) -> bytes:
    """Return the encryption key, preferring env var override."""
    env_key = os.environ.get("TALLY_ENCRYPTION_KEY")
    if env_key:
        key = env_key.encode()
        validate_fernet_key(key)
        return key
    return load_key(key_path)


def encrypt_value(plaintext: str, key: bytes) -> str:
    """Encrypt a string with the given Fernet key."""
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str, key: bytes) -> str:
    """Decrypt a Fernet-encrypted string."""
    return Fernet(key).decrypt(ciphertext.encode()).decode()


# Fernet tokens always start with "gAAAAA" (base64 of version
# byte 0x80 + 8-byte timestamp).
_FERNET_PREFIX = "gAAAAA"


def try_decrypt(raw: str, key: bytes) -> str:
    """Decrypt if the data looks like a Fernet token, else return as-is.

    Raises on decryption failure for data that IS encrypted
    (prevents silent fallback to plaintext on wrong-key errors).
    """
    if not raw.startswith(_FERNET_PREFIX):
        return raw
    return decrypt_value(raw, key)
