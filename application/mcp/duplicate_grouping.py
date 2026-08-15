"""Duplicate-candidate grouping for MCP-ingested findings (TAL-148).

Two findings are grouped as candidate duplicates when they share the
same file, the same rule_id family prefix (substring through the first
dot), and their line ranges either overlap or fall within a proximity
window. Grouping is transitive via union-find.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True)
class GroupableFinding:
    id: int
    file: str | None
    rule_id: str | None
    line_start: int | None
    line_end: int | None


@dataclass(frozen=True)
class _ValidFinding:
    id: int
    file: str
    rule_id: str
    line_start: int
    line_end: int | None


def _family(rule_id: str) -> str:
    if "." in rule_id:
        return rule_id.split(".", 1)[0] + "."
    return rule_id


def _normalize_line_end(line_end: int | None, line_start: int) -> int:
    return line_end if line_end is not None else line_start


def _ranges_qualify(
    line_start1: int,
    line_end1: int,
    line_start2: int,
    line_end2: int,
    proximity: int,
) -> bool:
    if not (line_end1 < line_start2 or line_end2 < line_start1):
        return True
    if line_end1 < line_start2:
        return line_start2 - line_end1 <= proximity
    return line_start1 - line_end2 <= proximity


class UnionFind:
    def __init__(self, items: list[int]) -> None:
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def find(self, x: int) -> int:
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x == root_y:
            return
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1


def group_duplicate_candidates(
    findings: list[GroupableFinding],
    proximity: int = 10,
) -> list[list[int]]:
    """Return candidate duplicate groups.

    Each returned group has two or more finding IDs. Groups and members
    within a group are sorted for deterministic output.
    """
    valid_list: list[_ValidFinding] = []
    for f in findings:
        if f.file is not None and f.rule_id is not None and f.line_start is not None:
            valid_list.append(
                cast(
                    _ValidFinding,
                    _ValidFinding(
                        id=f.id,
                        file=f.file,
                        rule_id=f.rule_id,
                        line_start=f.line_start,
                        line_end=f.line_end,
                    ),
                )
            )

    if len(valid_list) < 2:
        return []

    uf = UnionFind([f.id for f in valid_list])

    for i, f1 in enumerate(valid_list):
        for f2 in valid_list[i + 1 :]:
            if f1.file != f2.file:
                continue
            if _family(f1.rule_id) != _family(f2.rule_id):
                continue
            line_end1 = _normalize_line_end(f1.line_end, f1.line_start)
            line_end2 = _normalize_line_end(f2.line_end, f2.line_start)
            if _ranges_qualify(
                f1.line_start, line_end1, f2.line_start, line_end2, proximity
            ):
                uf.union(f1.id, f2.id)

    groups_dict: dict[int, list[int]] = {}
    for f in valid_list:
        root = uf.find(f.id)
        groups_dict.setdefault(root, []).append(f.id)

    result = [sorted(group) for group in groups_dict.values() if len(group) >= 2]
    result.sort(key=lambda g: g[0])
    return result
