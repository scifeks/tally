"""Unit tests for the prompt renderer mapping in TriageRunner."""

from __future__ import annotations

import pytest

from application.triage.runner import _PROMPT_RENDERERS


class TestPromptRenderers:
    def test_known_segments_render_strings(self) -> None:
        result = _PROMPT_RENDERERS["sast"]({"id": 1}, project="demo")
        assert isinstance(result, str)
        assert result

    def test_web_segment_not_registered(self) -> None:
        with pytest.raises(KeyError):
            _PROMPT_RENDERERS["web"]

    def test_unknown_segment_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            _PROMPT_RENDERERS["unknown"]
