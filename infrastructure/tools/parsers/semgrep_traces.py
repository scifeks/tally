"""Parse semgrep --text --dataflow-traces output.

Semgrep OSS computes taint traces but only exposes them in text
output, not JSON or SARIF.
"""

from __future__ import annotations

import re
from typing import Any

_LINE_RE = re.compile(r"^\s*(\d+)┆\s?(.*)$")
_RULE_RE = re.compile(r"^\s*❯+❱\s+(.+)$")


def parse_traces(text: str) -> list[dict[str, Any]]:
    """Parse taint trace records from semgrep text output."""
    results: list[dict[str, Any]] = []
    lines = text.splitlines()
    i = 0
    current_file = ""

    while i < len(lines):
        line = lines[i]

        if not line.strip().startswith("❯") and "/" in line:
            candidate = line.strip()
            if candidate and not candidate.startswith("❰"):
                stripped = candidate.rstrip()
                if _looks_like_path(stripped):
                    current_file = stripped

        rule_match = _RULE_RE.match(line)
        if rule_match:
            rule_id = rule_match.group(1).strip()
            i += 1
            i, traces = _parse_rule_block(
                lines,
                i,
                rule_id,
                current_file,
            )
            results.extend(traces)
            continue

        i += 1

    return results


def merge_traces(
    findings: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> None:
    """Merge trace data into parsed JSON findings in place.

    Matches by (rule_id, file_path, sink_line == line_start).
    """
    lookup: dict[tuple[str, str, int], list[dict]] = {}
    for t in traces:
        key = (
            t.get("rule_id", ""),
            t.get("file_path", ""),
            t.get("sink_line", 0),
        )
        lookup.setdefault(key, []).append(t)

    for finding in findings:
        key = (
            finding.get("rule_id", ""),
            finding.get("file_path", ""),
            finding.get("line_start", 0),
        )
        matched = lookup.get(key)
        if not matched:
            continue
        trace = matched[0]
        if trace.get("source_line") is not None:
            finding["sast_source_line"] = trace["source_line"]
        if trace.get("source_content"):
            finding["sast_source_object"] = trace["source_content"]
        if trace.get("sink_content"):
            finding["sast_sink_object"] = trace["sink_content"]
        if trace.get("intermediates"):
            finding["dataflow_trace"] = trace["intermediates"]
        src_file = trace.get("file_path", "")
        if src_file:
            finding["sast_source_file_path"] = src_file


def _looks_like_path(text: str) -> bool:
    if not text or "/" not in text:
        return False
    if text[0] in ('"', "'", "(", "{", "[", "$", "<"):
        return False
    if text.startswith("http") or text.startswith("Details:"):
        return False
    first = text.split("/")[0]
    return " " not in first


def _parse_rule_block(
    lines: list[str],
    start: int,
    rule_id: str,
    file_path: str,
) -> tuple[int, list[dict[str, Any]]]:
    traces: list[dict[str, Any]] = []
    i = start
    sink_line: int | None = None
    sink_content = ""

    while i < len(lines):
        line = lines[i]

        if _RULE_RE.match(line):
            break
        stripped = line.strip()
        if (
            _looks_like_path(stripped)
            and not stripped.startswith("❰")
            and not stripped.startswith("Details:")
        ):
            break

        if "Taint comes from:" in line:
            i += 1
            i, source_entries = _collect_code_lines(lines, i)
            i, intermediates = _parse_intermediates(lines, i)
            i, sink_entries = _parse_sink(lines, i)

            trace: dict[str, Any] = {
                "rule_id": rule_id,
                "file_path": file_path,
            }
            if source_entries:
                trace["source_line"] = source_entries[0][0]
                trace["source_content"] = source_entries[0][1]
            snk = sink_entries[0] if sink_entries else None
            trace["sink_line"] = snk[0] if snk else sink_line
            trace["sink_content"] = snk[1] if snk else sink_content
            if intermediates:
                trace["intermediates"] = intermediates
            traces.append(trace)
            continue

        code = _LINE_RE.match(line)
        if code and sink_line is None:
            sink_line = int(code.group(1))
            sink_content = code.group(2).strip()

        i += 1

    return i, traces


def _collect_code_lines(
    lines: list[str],
    start: int,
) -> tuple[int, list[tuple[int, str]]]:
    entries: list[tuple[int, str]] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if "Taint" in line or "taint" in line:
            break
        if _RULE_RE.match(line):
            break
        stripped = line.strip()
        if stripped and _looks_like_path(stripped):
            break
        code = _LINE_RE.match(line)
        if code:
            entries.append(
                (int(code.group(1)), code.group(2).strip()),
            )
        i += 1
    return i, entries


def _parse_intermediates(
    lines: list[str],
    start: int,
) -> tuple[int, list[dict[str, Any]]]:
    i = start
    if i < len(lines) and "intermediate" in lines[i]:
        i += 1
        i, entries = _collect_code_lines(lines, i)
        return i, [{"line": ln, "content": ct} for ln, ct in entries]
    return i, []


def _parse_sink(
    lines: list[str],
    start: int,
) -> tuple[int, list[tuple[int, str]]]:
    i = start
    if i < len(lines) and "taint reaches the sink" in lines[i]:
        i += 1
        return _collect_code_lines(lines, i)
    return i, []
