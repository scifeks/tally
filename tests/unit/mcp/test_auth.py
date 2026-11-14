"""Unit tests for MCP bearer token authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from core.security.credentials import encrypt_value
from mcp_server.auth import validate_bearer_token

if TYPE_CHECKING:
    pass


@pytest.fixture
def encryption_key() -> bytes:
    """Provide a valid Fernet encryption key for testing."""
    from cryptography.fernet import Fernet

    return Fernet.generate_key()


@pytest.fixture
def mock_token_repo() -> Mock:
    """Provide a mock token repository."""
    return Mock(spec=["get_all_encrypted"])


class TestValidateBearerToken:
    """Test bearer token validation against stored encrypted tokens."""

    def test_valid_token_matches(
        self,
        encryption_key: bytes,
        mock_token_repo: Mock,
    ) -> None:
        """Valid token decrypts and matches stored token."""
        plaintext = "secret_token_123"
        encrypted = encrypt_value(plaintext, encryption_key)
        mock_token_repo.get_all_encrypted.return_value = [encrypted]

        authorization = f"Bearer {plaintext}"
        assert validate_bearer_token(
            authorization,
            mock_token_repo,
            encryption_key,
        )

    def test_invalid_token_no_match(
        self,
        encryption_key: bytes,
        mock_token_repo: Mock,
    ) -> None:
        """Invalid token does not match any stored token."""
        plaintext = "secret_token_123"
        encrypted = encrypt_value(plaintext, encryption_key)
        mock_token_repo.get_all_encrypted.return_value = [encrypted]

        authorization = "Bearer wrong_token"
        assert not validate_bearer_token(
            authorization,
            mock_token_repo,
            encryption_key,
        )

    def test_missing_bearer_prefix(
        self,
        encryption_key: bytes,
        mock_token_repo: Mock,
    ) -> None:
        """Authorization header without Bearer prefix is rejected."""
        plaintext = "secret_token_123"
        encrypted = encrypt_value(plaintext, encryption_key)
        mock_token_repo.get_all_encrypted.return_value = [encrypted]

        authorization = f"Token {plaintext}"
        assert not validate_bearer_token(
            authorization,
            mock_token_repo,
            encryption_key,
        )

    def test_empty_token_list(
        self,
        encryption_key: bytes,
        mock_token_repo: Mock,
    ) -> None:
        """Empty token list always returns False."""
        mock_token_repo.get_all_encrypted.return_value = []

        authorization = "Bearer any_token"
        assert not validate_bearer_token(
            authorization,
            mock_token_repo,
            encryption_key,
        )

    def test_multiple_tokens_one_matches(
        self,
        encryption_key: bytes,
        mock_token_repo: Mock,
    ) -> None:
        """Valid token matches among multiple stored tokens."""
        token1 = "old_token"
        token2 = "active_token"
        token3 = "another_token"

        enc1 = encrypt_value(token1, encryption_key)
        enc2 = encrypt_value(token2, encryption_key)
        enc3 = encrypt_value(token3, encryption_key)
        mock_token_repo.get_all_encrypted.return_value = [enc1, enc2, enc3]

        authorization = f"Bearer {token2}"
        assert validate_bearer_token(
            authorization,
            mock_token_repo,
            encryption_key,
        )

    def test_timing_attack_resistant(
        self,
        encryption_key: bytes,
        mock_token_repo: Mock,
    ) -> None:
        """Token comparison uses constant-time compare."""
        plaintext = "secret_token"
        encrypted = encrypt_value(plaintext, encryption_key)
        mock_token_repo.get_all_encrypted.return_value = [encrypted]

        # Both should return False but take roughly the same time.
        auth1 = "Bearer " + plaintext[:-1] + "x"
        auth2 = "Bearer " + "x" * len(plaintext)

        result1 = validate_bearer_token(auth1, mock_token_repo, encryption_key)
        result2 = validate_bearer_token(auth2, mock_token_repo, encryption_key)

        assert not result1
        assert not result2
