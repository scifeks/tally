"""Static SPA (Single Page Application) detection for wizard-time use.

Two-layer detection:
1. Manifest sniff - parse package.json and look for known SPA framework deps.
2. Source-pattern grep - search JS/TS/HTML source files for SPA routing wiring.

Both layers short-circuit on the first positive match to keep startup fast.
Source grep is skipped entirely when the repo has no JS/TS files (e.g. pure
Python or PHP repos) so detection overhead is negligible for non-JS repos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Deps that reliably indicate a SPA, including scoped npm variants.
_SPA_DEPS: frozenset[str] = frozenset(
    {
        "react",
        "react-dom",
        "react-router",
        "react-router-dom",
        "@angular/core",
        "@angular/router",
        "vue",
        "vue-router",
        "nuxt",
        "svelte",
        "@sveltejs/kit",
        "next",
        "gatsby",
        "remix",
        "@remix-run/react",
        "vite",
    }
)

# Patterns found in SPA source wiring (not merely in deps).  Higher signal
# than a package.json entry because build tools like vite also appear in SSR
# apps without client-side routing.
_SPA_SOURCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"createBrowserRouter|BrowserRouter"), "React Router"),
    (re.compile(r"RouterModule\.forRoot"), "Angular Router"),
    (re.compile(r"createRouter\("), "Vue Router"),
    (re.compile(r"<router-view[\s/>]"), "Vue router-view"),
    (re.compile(r"ng-app=|ng-controller="), "AngularJS"),
]

_SKIP_DIRS: frozenset[str] = frozenset(
    {"node_modules", ".git", "dist", "build", ".next", ".nuxt", "out", "coverage"}
)

_SOURCE_EXTENSIONS: frozenset[str] = frozenset({".js", ".ts", ".jsx", ".tsx", ".html"})


def _sniff_manifest(repo_path: Path) -> tuple[bool, str]:
    """Return (True, reason) if package.json lists a known SPA dep."""
    pkg = repo_path / "package.json"
    if not pkg.is_file():
        return False, ""
    try:
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return False, ""

    all_deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        all_deps.update(data.get(key, {}).keys())

    matches = _SPA_DEPS & all_deps
    if matches:
        sample = sorted(matches)[0]
        return True, f"detected '{sample}' in package.json"
    return False, ""


def _grep_source(repo_path: Path) -> tuple[bool, str]:
    """Return (True, reason) if SPA routing wiring is found in source files."""
    for dirpath, dirnames, filenames in repo_path.walk():
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            if Path(filename).suffix not in _SOURCE_EXTENSIONS:
                continue
            filepath = dirpath / filename
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for pattern, label in _SPA_SOURCE_PATTERNS:
                if pattern.search(text):
                    rel = filepath.relative_to(repo_path)
                    return True, f"found {label} pattern in {rel}"
    return False, ""


def detect_spa(repo_path: str | Path) -> tuple[bool, str]:
    """Return ``(is_spa, reason)`` for the repo at *repo_path*.

    *reason* is a human-readable string explaining the detection trigger,
    suitable for display in the wizard prompt (e.g.
    "detected 'react-router-dom' in package.json").  It is empty when
    ``is_spa`` is False.

    The function returns quickly on the first positive signal.  On repos
    with no package.json and no JS/TS files it returns ``(False, "")``
    with minimal I/O.
    """
    path = Path(repo_path)
    if not path.is_dir():
        return False, ""

    # Layer 1: manifest sniff (cheapest - single file read).
    found, reason = _sniff_manifest(path)
    if found:
        return True, reason

    # Layer 2: source-pattern grep (skip repos with no JS/TS files at root
    # level to short-circuit pure-backend repos without a full walk).
    found, reason = _grep_source(path)
    return found, reason
