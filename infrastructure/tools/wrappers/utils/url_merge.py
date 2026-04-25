"""URLMerger: merges and normalises URLs from Katana, Noir, and user sources.

Facade pattern — hides the complexity of reading multiple OAS3 files,
joining Noir/Katana URI paths with the repo base URL, and deduplicating
the result.

Sources (all optional, all read from disk):
- Katana OAS3 — ``tool_outputs/katana/<repo>_*_oas3.json``
- Noir OAS3   — ``tool_outputs/noir/<repo>_*_oas3.json``
- User OAS3   — ``repo.oas3_path`` (user-provided endpoint file)

Normalisation rules applied before deduplication:
- Lowercase the host.
- Remove default ports (80 for http, 443 for https).
- Strip trailing slashes from paths (except root ``/``).
- Scheme differences (http vs https) are ignored — compare by
  ``host:port/path``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from core.project_paths import ProjectPaths
from infrastructure.tools.wrappers.utils.scope import in_scope

logger = logging.getLogger(__name__)


def _normalise_url(url: str) -> str:
    """Return a canonical comparison key for *url*.

    Used only for deduplication — the original URL is preserved in output.
    """
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        scheme = parsed.scheme.lower()
        port = parsed.port
        if (
            port is None
            or (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        ):
            netloc = host
        else:
            netloc = f"{host}:{port}"
        path = parsed.path.rstrip("/") or "/"
        key = f"{netloc}{path}"
        if parsed.query:
            key = f"{key}?{parsed.query}"
        return key
    except Exception:
        return url.lower().rstrip("/")


class URLMerger:
    """Merge URL sources into a single deduplicated list.

    Usage::

        merger = URLMerger(
            base_path=base_path,
            project_name=project_name,
            repo_name=repo.name,
            base_url=repo.base_urls[0],
            user_oas3_path=repo.oas3_path,
        )
        urls = merger.merge()
    """

    def __init__(
        self,
        base_path: str,
        project_name: str,
        repo_name: str,
        base_url: str,
        user_oas3_path: str = "",
    ) -> None:
        self._base_path = base_path
        self._project_name = project_name
        self._repo_name = repo_name
        self._base_url = base_url.rstrip("/")
        self._user_oas3_path = user_oas3_path

    def merge(self) -> list[str]:
        """Return a deduplicated, normalised list of full URLs.

        Sources are read in priority order: Katana → Noir → user.
        Deduplication preserves first-seen order.
        """
        raw: list[str] = []

        for path in self._load_latest_oas3(self._katana_dir()):
            raw.append(self._to_full_url(path))

        for path in self._load_latest_oas3(self._noir_dir()):
            raw.append(self._to_full_url(path))

        if self._user_oas3_path:
            user_file = Path(self._user_oas3_path)
            if user_file.exists():
                for path in self._load_paths_from_file(user_file):
                    raw.append(self._to_full_url(path))

        scoped = [u for u in raw if in_scope(u, self._base_url)]
        dropped = len(raw) - len(scoped)
        if dropped:
            logger.info(
                "URLMerger: dropped %d out-of-scope URLs (base=%r)",
                dropped,
                self._base_url,
            )

        return self._deduplicate(scoped)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _project_paths(self) -> ProjectPaths:
        return ProjectPaths.from_canonical(self._base_path, self._project_name)

    def _katana_dir(self) -> Path:
        return self._project_paths().tool_output_dir("katana")

    def _noir_dir(self) -> Path:
        return self._project_paths().tool_output_dir("noir")

    def _load_latest_oas3(self, tool_dir: Path) -> list[str]:
        """Return OAS3 path keys from the most recent matching file in *tool_dir*."""
        if not tool_dir.exists():
            return []
        matches = sorted(tool_dir.glob(f"{self._repo_name}_*_oas3.json"))
        if not matches:
            return []
        return self._load_paths_from_file(matches[-1])

    def _load_paths_from_file(self, oas3_path: Path) -> list[str]:
        """Return OAS3 ``paths`` dict keys from *oas3_path*."""
        try:
            data = json.loads(oas3_path.read_text(encoding="utf-8"))
            return list(data.get("paths", {}).keys())
        except (OSError, json.JSONDecodeError, ValueError):
            logger.warning("URLMerger: could not read %s", oas3_path)
            return []

    def _to_full_url(self, path: str) -> str:
        """Convert a URI path to a full URL using ``self._base_url``.

        Paths that already carry a scheme (e.g. Katana OAS3 entries that
        were generated from full crawl URLs) are returned unchanged.
        """
        if path.startswith(("http://", "https://")):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self._base_url + path

    def _deduplicate(self, urls: list[str]) -> list[str]:
        """Deduplicate *urls* by normalised key, preserving insertion order."""
        seen: set[str] = set()
        result: list[str] = []
        for url in urls:
            key = _normalise_url(url)
            if key not in seen:
                seen.add(key)
                result.append(url)
        return result
