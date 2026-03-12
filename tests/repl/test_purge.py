"""Tests for the purge command (PurgeCommand)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.repl.commands.purge import PurgeCommand  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repl(tmp_path: Path, active_project: str = "testproj") -> MagicMock:
    """Return a minimal REPL mock with a real tmp_path as base_path."""
    repl = MagicMock()
    repl.active_project = active_project
    repl.base_path = str(tmp_path)
    repl.console = MagicMock()
    return repl


def _make_rag_engine(doc_count: int = 5) -> MagicMock:
    """Return a RAGEngine mock that reports doc_count documents."""
    engine = MagicMock()
    engine._collection = MagicMock()
    engine._collection.get.return_value = {"ids": [f"id-{i}" for i in range(doc_count)]}
    engine.count_documents.return_value = doc_count
    engine.delete_findings.return_value = doc_count
    return engine


MOCK_TOOLS = ["nmap", "semgrep", "gitleaks", "zap", "pip-audit"]


def _run_purge(
    args: list[str],
    tools: list[str] = MOCK_TOOLS,
    doc_count: int = 5,
    answer: str = "y",
    tmp_path: Path | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Run cmd_purge with mocked engine and tool_registry."""
    repl = MagicMock()
    repl.active_project = "testproj"
    repl.base_path = str(tmp_path) if tmp_path else "/tmp"
    repl.console = MagicMock()
    engine = _make_rag_engine(doc_count)
    cmd = PurgeCommand(repl)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value=answer) as mock_input,
    ):
        mock_reg.list_tool_names.return_value = tools
        cmd.cmd_purge("purge", args)
    return repl, engine, mock_input


# ---------------------------------------------------------------------------
# Positional-arg rejection
# ---------------------------------------------------------------------------


def test_bare_positional_arg_rejected(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    with patch("core.repl.commands.purge.tool_registry"):
        cmd.cmd_purge("purge", ["gitleaks"])
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "Unrecognized" in printed


def test_multiple_positional_args_rejected(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    with patch("core.repl.commands.purge.tool_registry"):
        cmd.cmd_purge("purge", ["foo", "bar"])
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "Unrecognized" in printed


def test_positional_arg_does_not_delete_anything(tmp_path: Path) -> None:
    """No deletion should occur when bare positional args are passed."""
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    with (
        patch.object(cmd, "_get_rag_engine") as mock_engine,
        patch("core.repl.commands.purge.tool_registry"),
    ):
        cmd.cmd_purge("purge", ["nmap"])
    mock_engine.assert_not_called()


# ---------------------------------------------------------------------------
# No active project
# ---------------------------------------------------------------------------


def test_no_active_project_prints_warning(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    repl.active_project = None
    cmd = PurgeCommand(repl)
    cmd.cmd_purge("purge", [])
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "No active project" in printed


# ---------------------------------------------------------------------------
# Abort on non-'y' input
# ---------------------------------------------------------------------------


def test_abort_on_no_answer(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(3)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="n"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", [])
    engine.delete_findings.assert_not_called()
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "Aborted" in printed


# ---------------------------------------------------------------------------
# Confirmation prompt contains [y/N]
# ---------------------------------------------------------------------------


def test_prompt_contains_yn(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(3)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="n"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", [])
    # The prompt line should contain [y/N] text
    prompt_calls = [str(c) for c in repl.console.print.call_args_list]
    assert any("[y/N]" in c for c in prompt_calls)


# ---------------------------------------------------------------------------
# Tool output file deletion
# ---------------------------------------------------------------------------


def test_purge_all_deletes_tool_output_files(tmp_path: Path) -> None:
    proj_dir = tmp_path / "projects" / "testproj"
    nmap_dir = proj_dir / "tool_outputs" / "nmap"
    gitleaks_dir = proj_dir / "tool_outputs" / "gitleaks"
    nmap_dir.mkdir(parents=True)
    gitleaks_dir.mkdir(parents=True)
    (nmap_dir / "scan.stdout").write_text("data")
    (gitleaks_dir / "results.json").write_text("data")

    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(5)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", [])

    assert not list(nmap_dir.iterdir())
    assert not list(gitleaks_dir.iterdir())
    assert nmap_dir.exists()
    assert gitleaks_dir.exists()


def test_purge_tool_deletes_only_that_tools_files(tmp_path: Path) -> None:
    proj_dir = tmp_path / "projects" / "testproj"
    nmap_dir = proj_dir / "tool_outputs" / "nmap"
    gitleaks_dir = proj_dir / "tool_outputs" / "gitleaks"
    nmap_dir.mkdir(parents=True)
    gitleaks_dir.mkdir(parents=True)
    (nmap_dir / "scan.stdout").write_text("data")
    gitleaks_file = gitleaks_dir / "results.json"
    gitleaks_file.write_text("data")

    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(3)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", ["--tool=nmap"])

    assert not list(nmap_dir.iterdir())
    assert nmap_dir.exists()
    # gitleaks files untouched
    assert gitleaks_file.exists()


def test_purge_tool_missing_dir_does_not_raise(tmp_path: Path) -> None:
    """tool_outputs/<tool> not existing should not crash the command."""
    proj_dir = tmp_path / "projects" / "testproj"
    proj_dir.mkdir(parents=True)

    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(2)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", ["--tool=nmap"])
    # No exception = pass


# ---------------------------------------------------------------------------
# ChromaDB delete_findings called correctly
# ---------------------------------------------------------------------------


def test_purge_all_calls_delete_findings_no_tool(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(5)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", [])
    engine.delete_findings.assert_called_once_with(tool=None)


def test_purge_tool_calls_delete_findings_with_tool(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(3)
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", ["--tool=nmap"])
    engine.delete_findings.assert_called_once_with(tool="nmap")


# ---------------------------------------------------------------------------
# Zero documents — no prompt shown
# ---------------------------------------------------------------------------


def test_zero_docs_skips_prompt(tmp_path: Path) -> None:
    repl = _make_repl(tmp_path)
    cmd = PurgeCommand(repl)
    engine = _make_rag_engine(0)
    engine.count_documents.return_value = 0
    with (
        patch.object(cmd, "_get_rag_engine", return_value=engine),
        patch("core.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y") as mock_input,
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", [])
    mock_input.assert_not_called()
    engine.delete_findings.assert_not_called()


# ---------------------------------------------------------------------------
# New tests: equals-sign syntax, multi-tool, invalid tool, old syntax rejection
# ---------------------------------------------------------------------------


def test_purge_no_args_triggers_confirmation_once(tmp_path: Path) -> None:
    _, engine, mock_input = _run_purge([], tmp_path=tmp_path)
    assert mock_input.call_count == 1
    engine.delete_findings.assert_called_once_with(tool=None)


def test_purge_single_tool_confirmation_once_names_tool(tmp_path: Path) -> None:
    repl, engine, mock_input = _run_purge(["--tool=semgrep"], tmp_path=tmp_path)
    assert mock_input.call_count == 1
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "semgrep" in printed


def test_purge_multi_tool_confirmation_once_names_both(tmp_path: Path) -> None:
    repl, engine, mock_input = _run_purge(["--tool=semgrep,nmap"], tmp_path=tmp_path)
    assert mock_input.call_count == 1
    assert engine.delete_findings.call_count == 2
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "semgrep" in printed
    assert "nmap" in printed


def test_purge_invalid_tool_prints_error_no_prompt(tmp_path: Path) -> None:
    repl, engine, mock_input = _run_purge(["--tool=badtool"], tmp_path=tmp_path)
    assert mock_input.call_count == 0
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "Unknown tool" in printed


def test_purge_old_syntax_rejected(tmp_path: Path) -> None:
    repl, engine, mock_input = _run_purge(["--tool", "semgrep"], tmp_path=tmp_path)
    assert mock_input.call_count == 0
    printed = " ".join(str(c) for c in repl.console.print.call_args_list)
    assert "--tool=" in printed or "equals sign" in printed
