"""Tests for Fernet credential encryption with passphrase-derived keys."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.security.credentials import (
    create_key_file,
    decrypt_value,
    encrypt_value,
    load_key,
    try_decrypt,
)


class TestKeyDerivation:
    def test_create_and_load_roundtrip(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        key = create_key_file("my-passphrase", key_path)
        loaded = load_key(key_path)
        assert key == loaded

    def test_key_file_permissions(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        create_key_file("passphrase", key_path)
        mode = key_path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_key_file_contains_salt_and_key(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        create_key_file("passphrase", key_path)
        data = json.loads(key_path.read_text())
        assert "salt" in data
        assert "key" in data
        assert "version" in data

    def test_different_passphrases_produce_different_keys(self, tmp_path: Path) -> None:
        k1 = create_key_file("alpha", tmp_path / "a.key")
        k2 = create_key_file("bravo", tmp_path / "b.key")
        assert k1 != k2

    def test_same_passphrase_different_salt_different_keys(
        self, tmp_path: Path
    ) -> None:
        k1 = create_key_file("same", tmp_path / "a.key")
        k2 = create_key_file("same", tmp_path / "b.key")
        assert k1 != k2


class TestEncryptDecrypt:
    def test_roundtrip(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        key = create_key_file("passphrase", key_path)
        ct = encrypt_value("secret-data", key)
        pt = decrypt_value(ct, key)
        assert pt == "secret-data"

    def test_encrypted_differs_from_plaintext(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        key = create_key_file("passphrase", key_path)
        ct = encrypt_value("secret-data", key)
        assert ct != "secret-data"

    def test_try_decrypt_unencrypted_returns_unchanged(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        key = create_key_file("passphrase", key_path)
        raw = '{"login_url": "http://x.com"}'
        result = try_decrypt(raw, key)
        assert result == raw

    def test_try_decrypt_encrypted_returns_plaintext(self, tmp_path: Path) -> None:
        key_path = tmp_path / "test.key"
        key = create_key_file("passphrase", key_path)
        ct = encrypt_value("secret", key)
        result = try_decrypt(ct, key)
        assert result == "secret"


class TestEnvVarOverride:
    def test_env_var_key_used_when_set(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.security.credentials import get_encryption_key

        key_path = tmp_path / "test.key"
        file_key = create_key_file("passphrase", key_path)

        env_key = create_key_file("other", tmp_path / "env.key")
        monkeypatch.setenv("TALLY_ENCRYPTION_KEY", env_key.decode())

        resolved = get_encryption_key(key_path)
        assert resolved == env_key
        assert resolved != file_key
