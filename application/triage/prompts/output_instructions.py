"""Verdict delivery instructions injected into renderers at render time."""

from __future__ import annotations

STDOUT_OUTPUT_INSTRUCTION = """\
## Output

Emit the verdict as a single JSON object as your final assistant
message. Nothing else: no markdown fences, no commentary, no leading
or trailing whitespace. The host parses the last JSON object it finds
in your final message."""

FILE_OUTPUT_INSTRUCTION = """\
## Output

Use the write tool to write the JSON object to
`/workspace/out/verdict.json`. The file MUST contain only the JSON
object: no markdown fences, no commentary, no leading or trailing
whitespace. Anything you say in chat is ignored; only the file
contents are read."""

MCP_TOOL_CALL_OUTPUT_INSTRUCTION = """\
## Output

Return the verdict JSON object by calling the `submit_verdicts` MCP
tool. Do not write to disk. Do not emit the verdict as plain text.
The tool call payload is the only channel the host reads."""
