"""Unit tests for ``domain.url_inventory.vendor_filter``.

The vendor / dependency rule used to live in the Noir parser. Phase
post-9.x moved it into the domain layer so the same rule serves every
URL provider (Noir, Katana, user-uploaded OAS3) at one ingest gate.
These tests pin the rule's contract directly — independent of any
adapter.
"""

from __future__ import annotations

import pytest

from domain.url_inventory.vendor_filter import VENDOR_INDICATORS, is_vendor_path


class TestStaticIndicators:
    """Built-in indicators are matched as anchored ``/<name>/`` segments."""

    @pytest.mark.parametrize(
        "path",
        [
            "/vendor/lib/router.php",
            "/node_modules/react/index.js",
            "/venv/lib/python.py",
            "/.venv/bin/activate",
            "/site-packages/django/views.py",
            "/__pycache__/module.pyc",
            "/build/artifact.zip",
            "/dist/package.tar.gz",
            "/.git/config",
            "/api/v1/vendor/inner/file.php",  # nested segment still matches
        ],
    )
    def test_detected(self, path: str) -> None:
        assert is_vendor_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "/api/users",
            "/vendor-api/users",  # contains "vendor" but not segment-anchored
            "/node/index.js",  # not /node_modules/
            "/builds",  # prefix-only, no trailing slash
            "/distribution/list",  # prefix-only
        ],
    )
    def test_not_detected(self, path: str) -> None:
        assert not is_vendor_path(path)

    def test_empty_string_returns_false(self) -> None:
        assert not is_vendor_path("")

    def test_case_insensitive(self) -> None:
        assert is_vendor_path("/VENDOR/foo")
        assert is_vendor_path("/Node_Modules/x")


class TestExtraIndicators:
    """``Repository.ignore_dirs`` values fold in alongside the static set."""

    def test_extra_dir_name_matches_segment(self) -> None:
        # User-configured "third_party" should be matched as /third_party/
        assert is_vendor_path(
            "/third_party/foo/bar.py", extra_indicators=["third_party"]
        )

    def test_extra_indicator_normalisation(self) -> None:
        # Leading/trailing slashes are stripped before re-anchoring; both
        # forms produce the same match.
        assert is_vendor_path("/cache/x.json", extra_indicators=["/cache/"])
        assert is_vendor_path("/cache/x.json", extra_indicators=["cache"])

    def test_extra_indicator_case_insensitive(self) -> None:
        assert is_vendor_path("/Internal-Lib/route", extra_indicators=["internal-lib"])

    def test_empty_extras_skipped(self) -> None:
        # Empty / whitespace strings in the iterable must not produce a
        # zero-length indicator that matches every path.
        assert not is_vendor_path("/api/users", extra_indicators=["", "  "])

    def test_extras_do_not_relax_static_rule(self) -> None:
        # Adding extras must not turn previously-clean paths into hits via
        # accidental substring matching.
        assert not is_vendor_path("/api/users", extra_indicators=["third_party"])


class TestExportedConstant:
    """``VENDOR_INDICATORS`` must remain a stable frozenset surface."""

    def test_is_frozenset(self) -> None:
        assert isinstance(VENDOR_INDICATORS, frozenset)

    def test_contains_expected_core_entries(self) -> None:
        # Spot-check: the indicators most likely to leak from real repos.
        for entry in ("/vendor/", "/node_modules/", "/.git/"):
            assert entry in VENDOR_INDICATORS
