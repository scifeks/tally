"""Parse and summarize Antares investigation traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def parse_trace_file(path: Path) -> list[dict[str, Any]]:
    """Read JSONL trace file, return list of event dicts.

    Skips malformed lines and returns empty list for empty files.
    Each event dict contains: timestamp, phase, payload, evidence_id.
    """
    events: list[dict[str, Any]] = []

    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []

    return events


def build_trace_summary(events: list[dict[str, Any]]) -> str:
    """Condense trace events into text summary for RAG ingestion.

    Includes: files examined, commands run, key conclusions.
    Capped at ~5000 chars for ChromaDB chunking.
    """
    if not events:
        return ""

    lines: list[str] = []

    tool_calls: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    messages: list[str] = []

    for event in events:
        phase = event.get("phase", "")
        payload = event.get("payload", {})

        if phase == "tool_call":
            tool_calls.append(payload)
        elif phase == "finding":
            findings.append(payload)
        elif phase == "message":
            content = payload.get("content", "")
            if content:
                messages.append(content)

    if tool_calls:
        lines.append("Tools used:")
        for tc in tool_calls[:5]:
            tool_name = tc.get("tool_name", "unknown")
            args = tc.get("arguments", {})
            lines.append(f"  - {tool_name}: {json.dumps(args)[:80]}")
        if len(tool_calls) > 5:
            lines.append(f"  ... and {len(tool_calls) - 5} more tool calls")

    if messages:
        lines.append("\nAnalysis:")
        for msg in messages[:3]:
            lines.append(f"  {msg[:200]}")
        if len(messages) > 3:
            lines.append(f"  ... ({len(messages) - 3} more messages)")

    if findings:
        lines.append("\nFindings:")
        for finding in findings[:5]:
            title = finding.get("title", "Unknown")
            cwe = finding.get("cwe_id", "")
            severity = finding.get("severity", "")
            file_path = finding.get("file_path", "")
            line_num = finding.get("line", "")

            file_part = f":{line_num}" if line_num else ""
            location = f"{file_path}{file_part}" if file_path else "(unknown)"

            parts = [title]
            if cwe:
                parts.append(f"({cwe})")
            if severity:
                parts.append(f"[{severity}]")
            parts.append(f"@ {location}")

            lines.append(f"  - {' '.join(parts)}")

        if len(findings) > 5:
            lines.append(f"  ... and {len(findings) - 5} more findings")

    summary = "\n".join(lines)
    if len(summary) > 5000:
        summary = summary[:4997] + "..."

    return summary


def build_trace_detail(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Structured timeline for finding detail rendering.

    Each entry has 'type', 'timestamp', and relevant content.
    Large model outputs truncated to 500 chars per turn.
    """
    detail_entries: list[dict[str, Any]] = []

    for event in events:
        timestamp = event.get("timestamp", 0.0)
        phase = event.get("phase", "")
        payload = event.get("payload", {})
        evidence_id = event.get("evidence_id")

        if phase == "tool_call":
            tool_name = payload.get("tool_name", "unknown")
            arguments = payload.get("arguments", {})
            detail_entries.append(
                {
                    "type": "tool_call",
                    "timestamp": timestamp,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "evidence_id": evidence_id,
                }
            )

        elif phase == "tool_result":
            tool_name = payload.get("tool_name", "unknown")
            result_summary = payload.get("result_summary", "")
            detail_entries.append(
                {
                    "type": "tool_result",
                    "timestamp": timestamp,
                    "tool_name": tool_name,
                    "result_summary": result_summary[:500],
                    "evidence_id": evidence_id,
                }
            )

        elif phase == "message":
            role = payload.get("role", "assistant")
            content = payload.get("content", "")
            detail_entries.append(
                {
                    "type": "message",
                    "timestamp": timestamp,
                    "role": role,
                    "content": content[:500],
                }
            )

        elif phase == "finding":
            title = payload.get("title", "")
            cwe_id = payload.get("cwe_id", "")
            file_path = payload.get("file_path", "")
            severity = payload.get("severity", "")
            detail_entries.append(
                {
                    "type": "finding",
                    "timestamp": timestamp,
                    "title": title,
                    "cwe_id": cwe_id,
                    "file_path": file_path,
                    "severity": severity,
                }
            )

        elif phase == "error":
            error_type = payload.get("type", "unknown")
            error_message = payload.get("message", "")
            detail_entries.append(
                {
                    "type": "error",
                    "timestamp": timestamp,
                    "error_type": error_type,
                    "error_message": error_message[:500],
                }
            )

        elif phase == "done":
            status = payload.get("status", "completed")
            detail_entries.append(
                {
                    "type": "done",
                    "timestamp": timestamp,
                    "status": status,
                }
            )

    return detail_entries


def locate_trace_files(
    data_dir: Path,
) -> dict[str, Path]:
    """Map CWE IDs to their trace file paths.

    Scans data_dir/traces for .investigation.jsonl files and parses
    them to extract which CWE IDs they cover. Returns a dict mapping
    CWE ID -> first trace file path containing that CWE.
    """
    cwe_to_trace: dict[str, Path] = {}

    traces_dir = data_dir / "traces"
    if not traces_dir.exists():
        return cwe_to_trace

    for trace_file in sorted(traces_dir.glob("*.investigation.jsonl")):
        events = parse_trace_file(trace_file)
        for event in events:
            if event.get("phase") == "finding":
                payload = event.get("payload", {})
                cwe_id = payload.get("cwe_id")
                if cwe_id and cwe_id not in cwe_to_trace:
                    cwe_to_trace[cwe_id] = trace_file

    return cwe_to_trace
