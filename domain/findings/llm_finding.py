"""Domain model for LLM-based security findings."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LlmFinding:
    """A security finding from an LLM-based scan."""

    file_path: str
    description: str
    severity: str
    confidence: str
    finding_type: list[str]
    segment: str
    reasoning: str = ""
    remediation: str = ""
    rule_id: str = ""
    line_number: int | None = None
    cwe: list[str] = field(default_factory=list)
    attack_vector: str = ""
    code_snippet: str = ""
