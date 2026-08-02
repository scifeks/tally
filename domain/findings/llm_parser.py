"""Parser for LLM security scan findings."""

from __future__ import annotations

import json
import re

from domain.findings.llm_finding import LlmFinding
from domain.tools.constants import CONFIDENCE_LEVELS, SEVERITY_LEVELS
from domain.tools.scan_types.models import SEGMENT_ORDER


def parse_llm_findings(raw: str) -> tuple[list[LlmFinding], list[str]]:
    """Parse raw LLM output into validated findings.

    Args:
        raw: Raw text output from LLM, optionally code-fenced JSON.

    Returns:
        Tuple of (findings, errors) where errors is a list of validation
        messages. A finding with validation errors is excluded from the
        findings list.
    """
    json_str = _extract_json(raw)
    if json_str is None:
        return [], ["Could not extract valid JSON from input"]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return [], [f"Invalid JSON: {e}"]

    if not isinstance(data, list):
        return [], ["JSON root must be an array"]

    findings = []
    errors = []

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"Item {i} is not a dict")
            continue

        finding, item_errors = _parse_finding(item, i)
        if item_errors:
            errors.extend(item_errors)
        if finding:
            findings.append(finding)

    return findings, errors


def _extract_json(text: str) -> str | None:
    """Extract JSON array from text, handling code fences.

    Tries to extract JSON from code-fenced blocks first, then falls back
    to treating the entire input as JSON.
    """
    # Try code-fenced JSON
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try the whole input as JSON
    text_stripped = text.strip()
    if text_stripped.startswith("[") and text_stripped.endswith("]"):
        return text_stripped

    return None


def _parse_finding(item: dict, index: int) -> tuple[LlmFinding | None, list[str]]:
    """Parse a single finding dict into an LlmFinding dataclass.

    Returns:
        Tuple of (finding, errors). If errors occur, finding is None.
    """
    errors = []

    # Extract required fields
    file_path = item.get("file_path", "")
    if not file_path or not isinstance(file_path, str):
        errors.append(f"Item {index}: missing or invalid file_path")

    description = item.get("description", "")
    if not description or not isinstance(description, str):
        errors.append(f"Item {index}: missing or invalid description")

    severity = item.get("severity", "")
    if not severity or not isinstance(severity, str):
        errors.append(f"Item {index}: missing or invalid severity")
    elif severity not in SEVERITY_LEVELS:
        errors.append(
            f"Item {index}: severity '{severity}' not in {sorted(SEVERITY_LEVELS)}"
        )

    confidence = item.get("confidence", "")
    if not confidence or not isinstance(confidence, str):
        errors.append(f"Item {index}: missing or invalid confidence")
    elif confidence not in CONFIDENCE_LEVELS:
        errors.append(
            f"Item {index}: confidence '{confidence}' not in "
            f"{sorted(CONFIDENCE_LEVELS)}"
        )

    finding_type_raw = item.get("finding_type")
    if not isinstance(finding_type_raw, list) or not finding_type_raw:
        errors.append(f"Item {index}: finding_type must be a non-empty list")
        finding_type: list[str] = []
    else:
        for ft in finding_type_raw:
            if not isinstance(ft, str):
                errors.append(f"Item {index}: finding_type contains non-string: {ft}")
        finding_type = finding_type_raw

    segment = item.get("segment", "")
    if not segment or not isinstance(segment, str):
        errors.append(f"Item {index}: missing or invalid segment")
    elif segment not in SEGMENT_ORDER:
        errors.append(f"Item {index}: segment '{segment}' not in {SEGMENT_ORDER}")

    if errors:
        return None, errors

    # Extract optional fields
    reasoning = item.get("reasoning", "")
    if reasoning and not isinstance(reasoning, str):
        reasoning = ""

    remediation = item.get("remediation", "")
    if remediation and not isinstance(remediation, str):
        remediation = ""

    rule_id = item.get("rule_id", "")
    if rule_id and not isinstance(rule_id, str):
        rule_id = ""

    line_number = item.get("line_number")
    if line_number is not None and not isinstance(line_number, int):
        errors.append(f"Item {index}: line_number must be int or null")
        return None, errors

    cwe = item.get("cwe", [])
    if isinstance(cwe, list):
        cwe = [c for c in cwe if isinstance(c, str)]
    else:
        cwe = []

    attack_vector = item.get("attack_vector", "")
    if attack_vector and not isinstance(attack_vector, str):
        attack_vector = ""

    code_snippet = item.get("code_snippet", "")
    if code_snippet and not isinstance(code_snippet, str):
        code_snippet = ""

    finding = LlmFinding(
        file_path=file_path,
        description=description,
        severity=severity,
        confidence=confidence,
        finding_type=finding_type,
        segment=segment,
        reasoning=reasoning,
        remediation=remediation,
        rule_id=rule_id,
        line_number=line_number,
        cwe=cwe,
        attack_vector=attack_vector,
        code_snippet=code_snippet,
    )

    return finding, []
