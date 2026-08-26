"""Unit tests for Burp confidence mapping and fingerprint parsing."""

import pytest

from domain.tools.burp.confidence import (
    determine_finding_status,
    map_burp_confidence,
    parse_fingerprint,
)


class TestMapBurpConfidence:
    @pytest.mark.parametrize(
        "burp_value,expected",
        [
            ("certain", "confirmed"),
            ("firm", "probable"),
            ("tentative", "potential"),
            ("CERTAIN", "confirmed"),
            ("Firm", "probable"),
            ("TENTATIVE", "potential"),
        ],
        ids=[
            "certain",
            "firm",
            "tentative",
            "certain-upper",
            "firm-mixed",
            "tentative-upper",
        ],
    )
    def test_maps_all_levels(self, burp_value: str, expected: str) -> None:
        assert map_burp_confidence(burp_value) == expected

    def test_unknown_value_defaults_to_potential(self) -> None:
        assert map_burp_confidence("unknown") == "potential"

    def test_empty_string_defaults_to_potential(self) -> None:
        assert map_burp_confidence("") == "potential"


class TestDetermineFindingStatus:
    def test_returns_confirmed(self) -> None:
        assert determine_finding_status() == "confirmed"


class TestParseFingerprint:
    def test_extracts_all_fields(self) -> None:
        fp = (
            ":type=CROSS_SITE_REQUEST_FORGERY"
            ":origin=https%3A%2F%2Fgoat.justinc.app"
            ":path=%2FWebGoat%2Flogin"
            ":variant=1"
        )
        result = parse_fingerprint(fp)
        assert result["type"] == "CROSS_SITE_REQUEST_FORGERY"
        assert result["origin"] == "https://goat.justinc.app"
        assert result["path"] == "/WebGoat/login"
        assert result["variant"] == "1"

    def test_handles_missing_fields(self) -> None:
        fp = ":type=SQL_INJECTION:variant=2"
        result = parse_fingerprint(fp)
        assert result["type"] == "SQL_INJECTION"
        assert result["variant"] == "2"
        assert "origin" not in result
        assert "path" not in result

    def test_empty_fingerprint(self) -> None:
        assert parse_fingerprint("") == {}

    def test_url_decodes_special_characters(self) -> None:
        fp = ":type=XSS:path=%2Fapp%2Fuser%3Fid%3D1"
        result = parse_fingerprint(fp)
        assert result["path"] == "/app/user?id=1"
