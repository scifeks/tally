"""Integration tests for McpTokenRepository."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.store.project_registry import (  # noqa: E402
    ProjectRegistryRepository,
)
from infrastructure.store.repositories.mcp_tokens import (  # noqa: E402
    McpTokenRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Initialize a registry database with schema."""
    registry = ProjectRegistryRepository(tmp_path / "tally.db")
    registry.init_schema()
    return tmp_path / "tally.db"


@pytest.fixture()
def repo(db_path: Path) -> McpTokenRepository:
    """Create a McpTokenRepository against the temp database."""
    return McpTokenRepository(db_path)


class TestCreateToken:
    def test_create_returns_id(self, repo: McpTokenRepository) -> None:
        token_id = repo.create("my-token", "encrypted_value_123")
        assert token_id > 0

    def test_create_persists_in_db(
        self, repo: McpTokenRepository, db_path: Path
    ) -> None:
        token_id = repo.create("my-token", "encrypted_value_123")
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT id, name, encrypted_token FROM mcp_tokens WHERE id = ?",
                (token_id,),
            ).fetchone()
        assert row is not None
        assert row[0] == token_id
        assert row[1] == "my-token"
        assert row[2] == "encrypted_value_123"

    def test_duplicate_name_raises_integrity_error(
        self, repo: McpTokenRepository
    ) -> None:
        repo.create("my-token", "encrypted_value_123")
        with pytest.raises(sqlite3.IntegrityError):
            repo.create("my-token", "encrypted_value_456")

    def test_created_at_is_set(self, repo: McpTokenRepository, db_path: Path) -> None:
        token_id = repo.create("my-token", "encrypted_value_123")
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT created_at FROM mcp_tokens WHERE id = ?",
                (token_id,),
            ).fetchone()
        assert row is not None
        assert row[0] is not None
        assert len(row[0]) > 0


class TestListAll:
    def test_list_all_returns_metadata_only(self, repo: McpTokenRepository) -> None:
        token_id = repo.create("my-token", "encrypted_value_123")
        rows = repo.list_all()
        assert len(rows) == 1
        row = rows[0]
        assert row.id == token_id
        assert row.name == "my-token"
        assert row.created_at is not None

    def test_list_all_does_not_expose_encrypted_token(
        self, repo: McpTokenRepository
    ) -> None:
        repo.create("my-token", "encrypted_value_123")
        rows = repo.list_all()
        # McpTokenRow should not have an encrypted_token attribute
        assert not hasattr(rows[0], "encrypted_token")

    def test_list_all_multiple_tokens(self, repo: McpTokenRepository) -> None:
        repo.create("token1", "enc1")
        repo.create("token2", "enc2")
        repo.create("token3", "enc3")
        rows = repo.list_all()
        names = [r.name for r in rows]
        assert len(names) == 3
        assert "token1" in names
        assert "token2" in names
        assert "token3" in names

    def test_list_all_empty(self, repo: McpTokenRepository) -> None:
        rows = repo.list_all()
        assert rows == []


class TestRevoke:
    def test_revoke_deletes_token(
        self, repo: McpTokenRepository, db_path: Path
    ) -> None:
        token_id = repo.create("my-token", "encrypted_value_123")
        success = repo.revoke("my-token")
        assert success is True
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT id FROM mcp_tokens WHERE id = ?",
                (token_id,),
            ).fetchone()
        assert row is None

    def test_revoke_nonexistent_returns_false(self, repo: McpTokenRepository) -> None:
        success = repo.revoke("nonexistent-token")
        assert success is False

    def test_revoke_removes_from_list_all(self, repo: McpTokenRepository) -> None:
        repo.create("token1", "enc1")
        repo.create("token2", "enc2")
        repo.revoke("token1")
        rows = repo.list_all()
        names = [r.name for r in rows]
        assert "token1" not in names
        assert "token2" in names


class TestGetAllEncrypted:
    def test_get_all_encrypted_returns_values(self, repo: McpTokenRepository) -> None:
        repo.create("token1", "encrypted_value_1")
        repo.create("token2", "encrypted_value_2")
        values = repo.get_all_encrypted()
        assert len(values) == 2
        assert "encrypted_value_1" in values
        assert "encrypted_value_2" in values

    def test_get_all_encrypted_empty(self, repo: McpTokenRepository) -> None:
        values = repo.get_all_encrypted()
        assert values == []

    def test_get_all_encrypted_after_revoke(self, repo: McpTokenRepository) -> None:
        repo.create("token1", "encrypted_value_1")
        repo.create("token2", "encrypted_value_2")
        repo.revoke("token1")
        values = repo.get_all_encrypted()
        assert len(values) == 1
        assert "encrypted_value_2" in values
        assert "encrypted_value_1" not in values
