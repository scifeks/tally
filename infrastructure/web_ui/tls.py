"""Self-signed TLS certificate generation for the web UI."""

from __future__ import annotations

import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_CERT_VALIDITY_DAYS = 365


def tls_paths(base_path: str) -> tuple[Path, Path]:
    """Return the canonical (cert_path, key_path) without generating."""
    tls_dir = (Path(base_path) / "config" / "tls").resolve()
    return tls_dir / "cert.pem", tls_dir / "key.pem"


def ensure_tls_cert(base_path: str, host: str) -> tuple[Path, Path]:
    """Return (cert_path, key_path), generating a self-signed pair if absent."""
    cert_path, key_path = tls_paths(base_path)

    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    return regenerate_tls_cert(base_path, host)


def regenerate_tls_cert(base_path: str, host: str) -> tuple[Path, Path]:
    """Delete any existing cert/key and generate a fresh pair."""
    cert_path, key_path = tls_paths(base_path)
    tls_dir = cert_path.parent
    tls_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tls_dir, 0o700)
    cert_path.unlink(missing_ok=True)
    key_path.unlink(missing_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])

    san_entries: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    try:
        san_entries.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        san_entries.append(x509.DNSName(host))

    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=_CERT_VALIDITY_DAYS))
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(str(key_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key_bytes)

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return cert_path, key_path
