"""Unit tests for ffuf wordlist config resolution."""

from unittest.mock import patch

from infrastructure.tools.wrappers.base.ffuf import resolve_wordlists


class TestResolveWordlists:
    """resolve_wordlists returns valid paths in priority order."""

    @patch("pathlib.Path.exists", return_value=True)
    def test_config_path_used_when_exists(self, _exists):
        result = resolve_wordlists(["/custom/wordlist.txt"])
        assert result == ["/custom/wordlist.txt"]

    @patch("pathlib.Path.exists", return_value=True)
    def test_all_valid_configured_paths_returned(self, _exists):
        result = resolve_wordlists(["/a.txt", "/b.txt"])
        assert result == ["/a.txt", "/b.txt"]

    def test_config_path_skipped_when_missing(self):
        result = resolve_wordlists(["/nonexistent/path.txt"])
        assert "/nonexistent/path.txt" not in result

    def test_empty_config_falls_through(self):
        result = resolve_wordlists([])
        assert isinstance(result, list)
