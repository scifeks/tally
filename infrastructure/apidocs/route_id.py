#!/usr/bin/env python3
"""Stable route IDs for the apidocs pipeline.

route_id.py METHOD PATH APP VERSION  -> prints 12-hex id
route_id.py --check FILE             -> verifies ids + uniqueness
"""

import hashlib
import json
import re
import sys

PARAM = re.compile(
    r"(\{[^}]*\}|:[A-Za-z_][A-Za-z0-9_]*|<[^>]*>|\[\.{3}[^\]]*\]|\[[^\]]*\])"
)


def normalize_path(path: str) -> str:
    p = PARAM.sub("{}", path.strip())
    p = p.lower().rstrip("/")
    return p or "/"


def route_id(method: str, path: str, app: str, api_version: str) -> str:
    key = f"{method.upper()}|{normalize_path(path)}|{app}|{api_version or ''}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def check(fname: str) -> int:
    seen, bad = {}, 0
    for i, line in enumerate(open(fname), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        expect = route_id(r["method"], r["path"], r["app"], r.get("api_version", ""))
        if r["id"] != expect:
            method, path = r["method"], r["path"]
            print(f"line {i}: id {r['id']} != computed {expect} for {method} {path}")
            bad += 1
        if r["id"] in seen:
            print(f"line {i}: duplicate id {r['id']} (first at line {seen[r['id']]})")
            bad += 1
        seen[r["id"]] = i
    print(f"{len(seen)} routes, {bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2]))
    if len(sys.argv) == 5:
        print(route_id(*sys.argv[1:5]))
    else:
        sys.exit(__doc__)
