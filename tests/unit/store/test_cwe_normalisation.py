"""Unit tests for normalise_cwe."""

from __future__ import annotations

import json

from infrastructure.store.repositories.findings_serial import normalise_cwe


class TestCweNormalisationUnit:
    def test_none_returns_none(self) -> None:
        assert normalise_cwe(None) is None

    def test_int_produces_cwe_prefix(self) -> None:
        result = normalise_cwe(89)
        assert result is not None
        assert json.loads(result) == ["CWE-89"]

    def test_plain_string(self) -> None:
        result = normalise_cwe("CWE-89")
        assert result is not None
        assert json.loads(result) == ["CWE-89"]

    def test_list_input(self) -> None:
        result = normalise_cwe(["CWE-89", "CWE-20"])
        assert result is not None
        items = json.loads(result)
        assert "CWE-89" in items
        assert "CWE-20" in items

    def test_comma_joined_string(self) -> None:
        result = normalise_cwe("CWE-89, CWE-20")
        assert result is not None
        items = json.loads(result)
        assert "CWE-89" in items
        assert "CWE-20" in items

    def test_negative_int_returns_none(self) -> None:
        assert normalise_cwe(-1) is None

    def test_zero_returns_none(self) -> None:
        assert normalise_cwe(0) is None
