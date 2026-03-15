"""Scan result presentation for the tally REPL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.tools.base import ToolResult

if TYPE_CHECKING:
    from rich.console import Console


class ScanResultPresenter:
    """Present scan results to the user via the Rich console.

    Dispatches per-tool presentation. Replaces the _print_<tool>_result()
    and _summarize_<tool>() methods that were scattered on ScanCommands.
    """

    def __init__(self, console: Console) -> None:
        self._console = console

    def present(self, result: ToolResult) -> None:
        """Print a human-readable summary of result to the console."""
        tool = result.tool_name
        if tool == "gitleaks":
            self._present_gitleaks(result)
        elif tool == "semgrep":
            self._present_semgrep(result)
        elif tool in ("osv-scanner", "pip-audit", "npm-audit", "composer-audit"):
            self._present_sca(result, tool)
        elif tool == "zap":
            self._present_zap(result)
        else:
            self._present_generic(result)

    # ------------------------------------------------------------------
    # Per-tool presentation
    # ------------------------------------------------------------------

    def _present_gitleaks(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            data = result.parsed_data or {}
            total = data.get("summary", {}).get("total_secrets", 0)
            if total > 0:
                self._console.print("[yellow]⚠  WARNING: Secrets detected![/yellow]")
            summary = self._summarize_gitleaks(result)
            self._console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self._console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_gitleaks(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_secrets", 0)
        if total == 0:
            return "0 secrets found (clean)"
        files_count = summary.get("files_with_secrets", 0)
        by_rule = summary.get("by_rule", {})
        rule_str = ", ".join(f"{count} {rule}" for rule, count in by_rule.items())
        return f"{total} secrets in {files_count} file(s) ({rule_str})"

    def _present_semgrep(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_semgrep(result)
            self._console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self._console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_semgrep(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_findings", 0)
        by_sev = summary.get("by_severity", {})
        parts = [f"{by_sev[s]} {s}" for s in ("high", "medium", "low") if by_sev.get(s)]
        sev_str = ", ".join(parts) if parts else "none"
        return f"{total} findings ({sev_str})"

    def _present_sca(self, result: ToolResult, tool_name: str) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_sca(result)
            self._console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self._console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_sca(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_vulnerabilities", 0)
        by_sev = summary.get("by_severity", {})
        parts = [
            f"{by_sev[s]} {s}"
            for s in ("critical", "high", "medium", "low")
            if by_sev.get(s)
        ]
        sev_str = ", ".join(parts) if parts else "none"
        return f"{total} vulnerabilities ({sev_str})"

    def _present_zap(self, result: ToolResult) -> None:
        has_valid_data = result.parsed_data and "error" not in result.parsed_data
        if has_valid_data or result.success:
            summary = self._summarize_zap(result)
            self._console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self._console.print(f"[red]✗ Scan failed:[/red] {result.output[:200]}")

    @staticmethod
    def _summarize_zap(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        summary = result.parsed_data.get("summary", {})
        total = summary.get("total_alerts", 0)
        by_risk = summary.get("by_risk", {})
        parts = [
            f"{by_risk[r]} {r}"
            for r in ("high", "medium", "low", "informational")
            if by_risk.get(r)
        ]
        risk_str = ", ".join(parts) if parts else "none"
        urls = summary.get("urls_scanned", 0)
        return f"{total} alerts ({risk_str}), {urls} URLs scanned"

    def _present_generic(self, result: ToolResult) -> None:
        """Fallback for tools without specific presentation logic (e.g. nmap)."""
        if result.success:
            summary = self._summarize_generic(result)
            self._console.print(f"[green]✓ Scan complete:[/green] {summary}")
        else:
            self._console.print(f"[red]✗ Scan failed:[/red] {result.output}")

    @staticmethod
    def _summarize_generic(result: ToolResult) -> str:
        if not result.parsed_data:
            return "scan complete"
        hosts = result.parsed_data.get("hosts", [])
        up_hosts = [h for h in hosts if h.get("state") == "up"]
        open_ports = sum(
            len([p for p in h.get("ports", []) if p.get("state") == "open"])
            for h in up_hosts
        )
        return f"{len(up_hosts)} hosts up, {open_ports} open ports"
