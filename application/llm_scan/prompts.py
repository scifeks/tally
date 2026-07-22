"""Prompt assembly for LLM-based security scanning."""

from __future__ import annotations


def build_scan_prompt(
    tree: str,
    repo_name: str,
    repo_path: str,
) -> str:
    """Assemble the security scan prompt from a directory tree."""
    return _SCAN_PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        repo_path=repo_path,
        tree=tree,
    )


_SCAN_PROMPT_TEMPLATE = """\
You are a security auditor scanning the repository "{repo_name}" \
located at {repo_path}.

## Directory Structure

{tree}

## Instructions

Scan this codebase for security vulnerabilities. You have access to \
Read, Grep, Glob, and Bash tools. Use them to examine source files.

Focus on:
- Injection flaws (SQL, command, LDAP, XPath)
- Authentication and session management weaknesses
- Sensitive data exposure (hardcoded secrets, API keys, credentials)
- Broken access control
- Security misconfiguration
- Cross-site scripting (XSS)
- Insecure deserialization
- Vulnerable dependencies
- Cryptographic failures
- Server-side request forgery (SSRF)

## Output Format

Return your findings as a JSON array. Each finding must have:

```json
[
  {{
    "file_path": "relative/path/to/file.py",
    "line_number": 42,
    "description": "Clear description of the vulnerability",
    "severity": "critical|high|medium|low|informational",
    "confidence": "confirmed|probable|possible",
    "finding_type": ["vulnerability"],
    "segment": "sast|sca|secrets|web",
    "reasoning": "Why this is a real vulnerability, with evidence",
    "remediation": "Specific fix recommendation",
    "rule_id": "short-kebab-case-identifier",
    "cwe": ["CWE-89"]
  }}
]
```

## Guidance

- Only report findings you have evidence for. Read the actual code.
- Classify severity based on real exploitability, not theoretical risk.
- Use "confirmed" confidence only when you can trace the data flow.
- Use "possible" for patterns that look suspicious but lack full context.
- Assign segment based on the vulnerability type: "sast" for code flaws, \
"secrets" for exposed credentials, "web" for web-specific issues, \
"sca" for dependency vulnerabilities.
- If you find no vulnerabilities, return an empty array: []
- Do not fabricate findings. An empty result is better than false \
positives.
"""
