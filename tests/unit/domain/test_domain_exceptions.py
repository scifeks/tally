"""Unit tests for InvalidSegmentError (domain.tools.exceptions)."""

from __future__ import annotations

import pytest

from domain.tools.exceptions import InvalidSegmentError


class TestInvalidSegmentError:
    def test_is_subclass_of_value_error(self) -> None:
        assert issubclass(InvalidSegmentError, ValueError)

    def test_is_subclass_of_exception(self) -> None:
        assert issubclass(InvalidSegmentError, Exception)

    def test_segment_name_attribute(self) -> None:
        err = InvalidSegmentError("bad", ["network", "sast"])
        assert err.segment_name == "bad"

    def test_valid_segments_attribute(self) -> None:
        err = InvalidSegmentError("bad", ["network", "sast"])
        assert err.valid_segments == ["network", "sast"]

    def test_message_contains_segment_name(self) -> None:
        err = InvalidSegmentError("bad", ["network"])
        assert "bad" in str(err)

    def test_catchable_as_value_error(self) -> None:
        with pytest.raises(ValueError, match="bad"):
            raise InvalidSegmentError("bad", ["network"])
