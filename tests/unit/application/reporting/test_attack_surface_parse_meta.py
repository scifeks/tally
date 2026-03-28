"""Unit tests for application.reporting.attack_surface._parse_meta."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.attack_surface import _parse_meta  # noqa: E402


class TestParseMeta(unittest.TestCase):
    """Tests for the module-level _parse_meta helper."""

    def test_string_json(self) -> None:
        result = _parse_meta({"meta": '{"key": "val"}'})
        self.assertEqual(result, {"key": "val"})

    def test_dict_passthrough(self) -> None:
        result = _parse_meta({"meta": {"key": "val"}})
        self.assertEqual(result, {"key": "val"})

    def test_invalid_json(self) -> None:
        result = _parse_meta({"meta": "not-json"})
        self.assertEqual(result, {})

    def test_none_meta(self) -> None:
        result = _parse_meta({"meta": None})
        self.assertEqual(result, {})

    def test_missing_meta_key(self) -> None:
        result = _parse_meta({})
        self.assertEqual(result, {})
