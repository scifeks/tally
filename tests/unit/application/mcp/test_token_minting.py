"""Tests for mint_bearer_token idempotency."""

from __future__ import annotations

from pathlib import Path

from application.mcp.token_minting import mint_bearer_token
from infrastructure.store.project_registry import ProjectRegistryRepository


def test_mint_bearer_token_is_idempotent_by_name(tmp_path: Path) -> None:
    """Repeated calls with the same tag succeed without IntegrityError."""
    ProjectRegistryRepository(tmp_path / "tally.db").init_schema()
    tag = "test-tag"
    first = mint_bearer_token(tag, base_path=tmp_path)
    second = mint_bearer_token(tag, base_path=tmp_path)
    assert first != second
