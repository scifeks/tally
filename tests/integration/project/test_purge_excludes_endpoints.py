"""Integration test: purge does not delete endpoints/ directory contents."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


class TestPurgeExcludesEndpoints:
    def test_full_purge_does_not_delete_endpoints(self, tmp_path: Path) -> None:
        """endpoints/ is preserved after a full tool-output purge."""
        from application.repl.commands.purge import PurgeCommand

        project_name = "test-proj"
        project_dir = tmp_path / "projects" / project_name

        # Create tool_outputs/ with a file that purge should remove
        semgrep_dir = project_dir / "tool_outputs" / "semgrep"
        semgrep_dir.mkdir(parents=True, exist_ok=True)
        output_file = semgrep_dir / "result.json"
        output_file.write_text("{}")

        # Create endpoints/original/ with a file purge must NOT touch
        endpoints_dir = project_dir / "endpoints" / "original"
        endpoints_dir.mkdir(parents=True, exist_ok=True)
        marker = endpoints_dir / "api.json"
        marker.write_text('{"openapi": "3.0.0"}')

        repl = MagicMock()
        repl.active_project = project_name
        repl.base_path = str(tmp_path)

        pc = PurgeCommand(repl)
        pc._delete_tool_output_files(tools=None)

        assert marker.exists(), "endpoints/ file must survive a full purge"
        assert not output_file.exists(), "tool_outputs/ file must be deleted by purge"
