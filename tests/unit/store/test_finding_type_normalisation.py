"""Unit tests for normalise_finding_type."""

from __future__ import annotations

import json

from infrastructure.store.repositories.findings_serial import normalise_finding_type


class TestFindingTypeNormalisation:
    def test_plain_string_secret(self) -> None:
        assert normalise_finding_type("secret") == '["secret"]'

    def test_already_array_is_idempotent(self) -> None:
        assert normalise_finding_type('["secret"]') == '["secret"]'

    def test_invalid_value_returns_none(self) -> None:
        result = normalise_finding_type("bogus")
        assert result is None

    def test_mixed_valid_and_invalid(self) -> None:
        result = normalise_finding_type('["secret", "bogus"]')
        assert result is not None
        items = json.loads(result)
        assert items == ["secret"]
        assert "bogus" not in items
