"""Unit tests for ffuf wordlist config resolution."""

from unittest.mock import patch

from infrastructure.tools.wrappers.base.ffuf import resolve_wordlist


class TestResolveWordlist:
    """resolve_wordlist checks config path first."""

    @patch("pathlib.Path.exists", return_value=True)
    def test_config_path_used_when_exists(self, _exists):
        result = resolve_wordlist("/custom/wordlist.txt")
        assert result == "/custom/wordlist.txt"

    def test_config_path_skipped_when_missing(self):
        result = resolve_wordlist("/nonexistent/path.txt")
        assert result != "/nonexistent/path.txt"

    def test_empty_config_path_falls_through(self):
        result = resolve_wordlist("")
        # Should not return empty string
        assert result != ""
