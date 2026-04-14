"""Katana local wrapper — runtime URL discovery via live crawling.

Invocation pattern
------------------
``katana -u <base_url> -d <depth> -jc -kf all -xhr -j -o <jsonl_file>``

Optional flags:
- ``-hl`` when ``katana_headless`` is True (headless Chrome mode)
- ``-H "Key: Value"`` per entry in ``katana_headers``

The ``-j`` flag writes JSONL to the file specified by ``-o``.
``build_command`` stores the JSONL path in ``self._last_jsonl_path``; after
the subprocess completes, ``parse_output`` reads that file, calls the
``KatanaAdapter`` to produce an OAS3 JSON document, and moves it to the
final ``<repo>_<ts>_oas3.json`` destination so downstream tools (ZAP,
XSStrike, DalFox) can consume it.

The OAS3 file is retained on disk (same as Noir) so that DAST tools can
discover it via glob helpers.  It is deleted only if the converted spec
contains zero paths (prevents downstream tools from importing an empty spec).
"""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.endpoints.converters.katana import KatanaAdapter
from infrastructure.tools.parsers.katana import parse_katana_jsonl
from infrastructure.tools.version import get_tool_version
from infrastructure.tools.wrappers.base.katana import BaseKatanaTool

logger = logging.getLogger(__name__)


class KatanaLocalTool(BaseKatanaTool):
    """Concrete local wrapper for the Katana binary."""

    def __init__(self, config=None) -> None:
        self._katana_path: str = config.path if config is not None else "katana"
        # Set by build_command(); read by parse_output().
        self._last_jsonl_path: Path | None = None
        self._last_oas3_path: Path | None = None

    @property
    def command(self) -> str:
        return "katana"

    def check_available(self) -> bool:
        return shutil.which("katana") is not None

    def get_version(self) -> str | None:
        return get_tool_version(self.command)

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the Katana argv list.

        Keyword Args:
            base_url (str): Target URL to crawl.  Required.
            output_file (str): Path for the JSONL output file.  Required.
            oas3_target (str): Destination path for the converted OAS3 file.
                Set by ``build_execution_passes``; used in ``parse_output``.
            depth (int): Crawl depth, passed as ``-d``.  Defaults to 3.
            headless (bool): Enable headless Chrome via ``-hl``.
            headers (dict[str, str]): Extra headers, each passed as
                ``-H "Key: Value"``.
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        output_file: str | None = (
            str(raw["output_file"]) if "output_file" in raw else None
        )
        oas3_target: str | None = (
            str(raw["oas3_target"]) if "oas3_target" in raw else None
        )
        depth: int = int(raw.get("depth", 3))  # type: ignore[arg-type]
        headless: bool = bool(raw.get("headless", False))
        headers: dict[str, str] | None = raw.get("headers") or None  # type: ignore[assignment]

        if not base_url:
            raise ValueError("base_url is required for katana")
        if not output_file:
            raise ValueError("output_file is required for katana")

        self._last_jsonl_path = Path(output_file)
        self._last_oas3_path = Path(oas3_target) if oas3_target else None

        cmd: list[str] = [
            self._katana_path,
            "-u", base_url,
            "-d", str(depth),
            "-jc",
            "-kf", "all",
            "-xhr",
            "-j",
            "-o", output_file,
        ]  # fmt: skip

        if headless:
            cmd.append("-hl")

        if headers:
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse Katana JSONL output and produce an OAS3 file for downstream tools.

        Steps:
        1. Resolve JSONL path from ``self._last_jsonl_path`` (fallback: files).
        2. Parse JSONL into structured endpoint data.
        3. Convert JSONL → OAS3 via ``KatanaAdapter``.
        4. Move ``endpoints.json`` to the timestamped ``_oas3.json`` target.
        5. Delete the OAS3 file if it contains zero paths (mirrors Noir).
        """
        try:
            jsonl_path: Path | None = self._last_jsonl_path
            if jsonl_path is None or not jsonl_path.exists():
                stdout_path = files.get("stdout")
                jsonl_path = (
                    stdout_path if stdout_path and stdout_path.exists() else None
                )

            if jsonl_path is None or not jsonl_path.exists():
                return {
                    "endpoints": [],
                    "summary": {"total_endpoints": 0},
                }

            parsed = parse_katana_jsonl(jsonl_path)

            # Convert JSONL → OAS3 so downstream DAST tools can consume it.
            katana_dir = jsonl_path.parent
            try:
                tmp_oas3 = KatanaAdapter().convert(jsonl_path, katana_dir)
                oas3_target = self._last_oas3_path
                if oas3_target is not None:
                    shutil.move(str(tmp_oas3), str(oas3_target))
                    final_oas3 = oas3_target
                else:
                    final_oas3 = tmp_oas3
            except Exception:
                logger.warning(
                    "Katana: OAS3 conversion failed for %s",
                    jsonl_path,
                    exc_info=True,
                )
                final_oas3 = None

            # Delete empty OAS3 (prevents ZAP from importing an empty spec).
            if final_oas3 is not None and final_oas3.exists():
                import json as _json

                try:
                    doc = _json.loads(final_oas3.read_text(encoding="utf-8"))
                    if not doc.get("paths"):
                        final_oas3.unlink()
                except Exception:
                    pass

            return parsed
        finally:
            self._last_jsonl_path = None
            self._last_oas3_path = None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for Katana.

        Skips (returns []) when ``repo.base_urls`` is empty — the generic
        orchestrator skip handles this, but we guard explicitly for safety.
        """
        assert context.repo is not None
        repo = context.repo

        if not repo.base_urls:
            logger.info(
                "Katana: no base_urls configured for %s — skipping",
                repo.name,
            )
            return []

        base_url = repo.base_urls[0]

        output_dir = (
            Path(context.base_path).resolve()
            / "projects"
            / context.project_name
            / "tool_outputs"
            / "katana"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        jsonl_file = str(output_dir / f"{repo.name}_{ts}.jsonl")
        oas3_file = str(output_dir / f"{repo.name}_{ts}_oas3.json")

        kwargs: dict[str, Any] = {
            "base_url": base_url,
            "output_file": jsonl_file,
            "oas3_target": oas3_file,
            "depth": repo.katana_depth,
            "headless": repo.katana_headless,
        }
        if repo.katana_headers:
            kwargs["headers"] = dict(repo.katana_headers)

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
