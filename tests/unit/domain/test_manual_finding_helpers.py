"""Unit tests for manual finding helpers."""

from __future__ import annotations

import pytest

from domain.findings.manual import derive_domain, manual_fingerprint


class TestDeriveDomain:
    @pytest.mark.parametrize(
        "segment,expected",
        [
            ("sast", "code"),
            ("sca", "code"),
            ("secrets", "code"),
            ("web", "web"),
            ("llm", "code"),
        ],
    )
    def test_maps_segment_to_domain(self, segment: str, expected: str) -> None:
        assert derive_domain(segment) == expected

    def test_unknown_segment_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown segment"):
            derive_domain("bogus")


class TestManualFingerprint:
    def test_deterministic(self) -> None:
        fp1 = manual_fingerprint("title", "sast", "src/app.py")
        fp2 = manual_fingerprint("title", "sast", "src/app.py")
        assert fp1 == fp2

    def test_differs_on_title(self) -> None:
        fp1 = manual_fingerprint("title-a", "sast", "src/app.py")
        fp2 = manual_fingerprint("title-b", "sast", "src/app.py")
        assert fp1 != fp2

    def test_is_sha256_hex(self) -> None:
        fp = manual_fingerprint("t", "sast", "f")
        assert len(fp) == 64
