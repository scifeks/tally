"""Unit tests for the static prompt renderer mapping in TriageRunner."""

from __future__ import annotations

import pytest

from application.triage.runner import _PROMPT_RENDERERS


class TestPromptRenderers:
    def test_known_segments_render_strings(self) -> None:
        for segment in ("api", "sast", "sca"):
            result = _PROMPT_RENDERERS[segment]([1, 2], "demo")
            assert isinstance(result, str)
            assert result

    def test_unknown_segment_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            _PROMPT_RENDERERS["unknown"]
