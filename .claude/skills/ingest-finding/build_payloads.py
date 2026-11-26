"""Build finding-add payloads from vulnerability report files.

Report text is copied into payload fields by this script, never retyped, so the
recorded finding holds exactly what the report says.

Usage: build_payloads.py <spec.json> <out_dir>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

CODE_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+\b")
TITLE_RE = re.compile(r"^# ([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d+): (.+)$")
HEADER_RE = re.compile(r"^- \*\*([^*]+):\*\* ?(.*)$")
DEFAULT_NOT_REF_PREFIXES = ("CVE-", "CWE-", "GHSA-", "ISO-", "SHA-", "UTF-")
PROSE_FIELDS = frozenset({"description", "attack_vector", "reasoning", "code_snippet"})
# finding-add silently drops meta keys that collide with these names.
RESERVED_META = frozenset(
    {
        "tool",
        "domain",
        "segment",
        "file",
        "file_path",
        "lockfile",
        "line_number",
        "line_start",
        "line_end",
        "description",
        "severity",
        "confidence",
        "cwe",
        "cwe_id",
        "cwe_ids",
        "finding_type",
        "rule_id",
        "repo_id",
        "reasoning",
        "attack_vector",
        "code_snippet",
    }
)
NO_REMEDIATION = "Not provided in source report."


class ReportError(Exception):
    """The report cannot be mapped without losing or inventing content."""


def _check_target(target: str) -> None:
    if target in PROSE_FIELDS:
        return
    if not target.startswith("meta.") or not target[5:]:
        raise ReportError(f"invalid target {target!r}")
    if target[5:] in RESERVED_META:
        raise ReportError(f"meta key {target[5:]!r} would be dropped by finding-add")


def _store(payload: dict[str, Any], target: str, value: str) -> None:
    _check_target(target)
    if target.startswith("meta."):
        holder, key = payload["meta"], target[5:]
    else:
        holder, key = payload, target
    if key in holder:
        raise ReportError(f"two parts of the report map to {target!r}")
    holder[key] = value


def internal_refs(text: str, own_code: str, not_refs: list[str]) -> list[str]:
    """Tracking codes mentioned in the report, other than the report's own."""
    return sorted(
        {
            code
            for code in CODE_RE.findall(text)
            if code != own_code
            and code not in not_refs
            and not code.startswith(DEFAULT_NOT_REF_PREFIXES)
        }
    )


def build_payload(
    text: str,
    *,
    section_map: dict[str, str],
    header_map: dict[str, str],
    classification: dict[str, Any],
    not_refs: list[str],
) -> dict[str, Any]:
    """Map one report onto a finding-add payload. Raises ReportError."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), 0)
    title_match = TITLE_RE.match(lines[first])
    if not title_match:
        raise ReportError("first line is not '# <CODE>: <title>'")
    code, title = title_match.groups()

    payload: dict[str, Any] = {"meta": {"title": title, "catalog_code": code}}
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines[first + 1 :]:
        if line.startswith("## "):
            current = line[3:].strip()
            if current in sections:
                raise ReportError(f"section {current!r} appears twice")
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
        elif header := HEADER_RE.match(line):
            label, value = header.groups()
            if label not in header_map:
                raise ReportError(f"header {label!r} is not in header_map")
            _store(payload, header_map[label], value)
        elif line.strip():
            preamble.append(line)

    if preamble:
        if "_preamble" not in header_map:
            raise ReportError("text before the first section is not mapped")
        _store(payload, header_map["_preamble"], "\n".join(preamble))

    for name, body in sections.items():
        if name not in section_map:
            raise ReportError(f"section {name!r} is not in section_map")
        _store(payload, section_map[name], "\n".join(body).strip("\n"))

    if "description" not in payload:
        raise ReportError("no section maps to description")
    payload["meta"].setdefault("remediation", NO_REMEDIATION)

    for key, value in classification.items():
        if key == "meta":
            for meta_key, meta_value in value.items():
                if meta_key in payload["meta"] or meta_key in RESERVED_META:
                    raise ReportError(f"classification sets meta.{meta_key}")
                payload["meta"][meta_key] = meta_value
        elif key in payload or key in PROSE_FIELDS:
            raise ReportError(f"classification sets report text field {key!r}")
        else:
            payload[key] = value

    payload["meta"]["internal_refs"] = internal_refs(text, code, not_refs)
    return payload


def main(spec_path: str, out_dir: str) -> int:
    from application.mcp.finding_payload import validate_finding_payload

    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    failed = False
    for entry in spec["reports"]:
        path = Path(entry["path"]).resolve()
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        try:
            payload = build_payload(
                text,
                section_map=spec["section_map"],
                header_map=spec.get("header_map", {}),
                classification=entry["classification"],
                not_refs=spec.get("not_refs", []),
            )
            code = payload["meta"]["catalog_code"]
            if code in seen:
                raise ReportError(f"code {code} appears in more than one report")
            seen.add(code)
            payload["meta"]["source_report_path"] = str(path)
            payload["meta"]["source_report_sha256"] = hashlib.sha256(raw).hexdigest()
            payload["meta"]["ingested_by"] = "ingest-finding"
            payload["meta"]["ingested_at"] = spec["ingested_at"]
            payload["meta"]["source_report"] = text
            validate_finding_payload(payload)
        except Exception as exc:
            print(f"FAIL\t{path}\t{exc}", file=sys.stderr)
            failed = True
            continue
        target = out / f"{code}.json"
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        print(f"OK\t{code}\t{entry['repo']}\t{target}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    sys.exit(main(sys.argv[1], sys.argv[2]))
