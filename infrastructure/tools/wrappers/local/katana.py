"""Katana local wrapper for runtime URL discovery via live crawling."""

from __future__ import annotations

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from application.ports.endpoint_converter import EndpointConverterPort
from core.project_paths import ProjectPaths
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.parsers.katana import parse_katana_jsonl
from infrastructure.tools.wrappers.base.katana import BaseKatanaTool
from infrastructure.tools.wrappers.utils.scope import scope_key

logger = logging.getLogger(__name__)


def _filter_jsonl_by_scope(jsonl_path: Path, base_url: str) -> None:
    """Remove JSONL lines whose endpoint host:port differs from *base_url*.

    Overwrites *jsonl_path* in-place.  Lines that cannot be parsed as JSON
    or that lack a ``request.endpoint`` field are kept unchanged.
    Reads line-by-line to avoid loading the full file into memory.
    """
    import json as _json

    allowed = scope_key(base_url)
    if allowed is None:
        logger.warning("Katana scope filter: could not parse base_url %r", base_url)
        return

    kept: list[str] = []
    dropped = 0
    try:
        with jsonl_path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = _json.loads(line)
                    endpoint = record.get("request", {}).get("endpoint", "")
                    if endpoint and scope_key(endpoint) != allowed:
                        dropped += 1
                        continue
                except Exception:
                    pass  # keep malformed lines
                kept.append(line)
    except OSError:
        return

    if dropped:
        logger.info(
            "Katana scope filter: dropped %d out-of-scope URLs (base=%r)",
            dropped,
            base_url,
        )

    jsonl_path.write_text("\n".join(kept) + "\n", encoding="utf-8")


class KatanaLocalTool(BaseKatanaTool):
    """Concrete local wrapper for the Katana binary."""

    def __init__(
        self, config=None, *, endpoint_converter: EndpointConverterPort
    ) -> None:
        self._endpoint_converter = endpoint_converter
        self._katana_path: str = config.path if config is not None else "katana"
        self._last_jsonl_path: Path | None = None
        self._last_oas3_path: Path | None = None
        self._last_base_url: str | None = None

    @property
    def command(self) -> str:
        return "katana"

    def check_available(self) -> bool:
        return shutil.which("katana") is not None

    def get_version(self) -> str | None:
        """Run ``katana -version`` and return the semver found in output.

        Katana prints an ASCII-art banner on the first line; the real
        version appears on a later line such as
        ``[INF] Current katana version v1.5.0 (latest)``.
        """
        import re
        import subprocess

        binary = shutil.which("katana")
        if binary is None:
            return None
        try:
            result = subprocess.run(
                [binary, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (result.stdout or result.stderr).strip()
            if not output:
                return None
            clean = re.sub(r"\x1b\[[0-9;]*m", "", output)
            match = re.search(r"\d+\.\d+[\d.]*", clean)
            return match.group(0) if match else None
        except Exception:
            return None

    # Crawl ceilings prevent infinite/multi-hour hangs when headless Chrome
    # stalls on a single page or cyclic parameterized routes produce
    # near-unbounded link graphs.
    _CRAWL_TIMEOUT_SECS = 15  # per-request HTTP timeout
    _CRAWL_CONCURRENCY = 10  # parallel browser/HTTP workers (-c)
    _CRAWL_PARALLELISM = 10  # parallel URL processing (-p)
    _CRAWL_RATE_LIMIT = 150  # max requests per second (-rl)
    _CRAWL_RETRIES = 1  # per-request retries (-retry)
    _CRAWL_MAX_DURATION = 900  # total crawl wall-clock ceiling in seconds (-ct)

    def build_command(self, **kwargs: object) -> list[str]:
        """Build the Katana argv list.

        Keyword Args:
            base_url (str): Target URL to crawl.  Required.
            output_file (str): Path for the JSONL output file.  Required.
            oas3_target (str): Destination path for the converted OAS3 file.
            depth (int): Crawl depth, passed as ``-d``.  Defaults to 5.
            headless (bool): Enable headless Chrome via ``-hl``.
            headers (dict[str, str]): Extra headers, each passed as
                ``-H "Key: Value"``.
            max_duration (int): Total crawl duration ceiling in seconds,
                passed as ``-ct``.  Defaults to ``_CRAWL_MAX_DURATION`` (900).
        """
        raw = kwargs or {}
        base_url: str | None = str(raw["base_url"]) if "base_url" in raw else None
        output_file: str | None = (
            str(raw["output_file"]) if "output_file" in raw else None
        )
        oas3_target: str | None = (
            str(raw["oas3_target"]) if "oas3_target" in raw else None
        )
        depth: int = int(raw.get("depth", 5))  # type: ignore[arg-type]
        headless: bool = bool(raw.get("headless", False))
        headers: dict[str, str] | None = raw.get("headers") or None  # type: ignore[assignment]
        max_duration: int = int(raw.get("max_duration", self._CRAWL_MAX_DURATION))  # type: ignore[arg-type]

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
            # Ceiling to prevent infinite crawls on cyclic/parameterized apps
            "-ct", str(max_duration),
            "-timeout", str(self._CRAWL_TIMEOUT_SECS),
            "-c", str(self._CRAWL_CONCURRENCY),
            "-p", str(self._CRAWL_PARALLELISM),
            "-rl", str(self._CRAWL_RATE_LIMIT),
            "-retry", str(self._CRAWL_RETRIES),
            "-silent",
        ]  # fmt: skip

        if headless:
            cmd.append("-hl")

        if headers:
            for key, value in headers.items():
                cmd.extend(["-H", f"{key}: {value}"])

        return cmd

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse JSONL output into endpoints and produce an OAS3 spec."""
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

            # Drop URLs outside the repo's configured scope before parsing.
            if self._last_base_url:
                _filter_jsonl_by_scope(jsonl_path, self._last_base_url)

            parsed = parse_katana_jsonl(jsonl_path)

            # Convert JSONL → OAS3 so downstream DAST tools can consume it.
            katana_dir = jsonl_path.parent
            try:
                tmp_oas3 = self._endpoint_converter.convert(jsonl_path, katana_dir)
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

            # Expose the OAS3 path through ``output_files`` so the URL
            # inventory ingest handler can read it from ToolResult.
            if final_oas3 is not None and final_oas3.exists():
                files["oas3"] = final_oas3

            return parsed
        finally:
            self._last_jsonl_path = None
            self._last_oas3_path = None
            self._last_base_url = None

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass for Katana.

        Skips (returns []) when ``service.base_urls`` is empty; the generic
        orchestrator skip handles this, but we guard explicitly for safety.
        """
        assert context.repo is not None
        assert context.service is not None
        repo = context.repo
        service = context.service

        if not service.base_urls:
            logger.info(
                "Katana: no base_urls configured for %s; skipping",
                repo.name,
            )
            return []

        base_url = service.base_urls[0]
        self._last_base_url = base_url

        output_dir = ProjectPaths.from_canonical(
            Path(context.base_path).resolve(), context.project_name
        ).tool_output_dir("katana")
        output_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        jsonl_file = str(output_dir / f"{repo.name}_{ts}.jsonl")
        oas3_file = str(output_dir / f"{repo.name}_{ts}_oas3.json")

        headers: dict[str, str] = dict(repo.katana_headers)

        if repo.auth is not None:
            from infrastructure.tools.wrappers.utils.auth_login import perform_login

            auth_headers = perform_login(repo.auth)
            if auth_headers:
                # Merge: auth-derived cookie wins if key already present.
                headers = {**headers, **auth_headers}

        kwargs: dict[str, Any] = {
            "base_url": base_url,
            "output_file": jsonl_file,
            "oas3_target": oas3_file,
            "depth": (
                service.katana_depth
                if service.katana_depth is not None
                else repo.katana_depth
            ),
            "headless": (
                service.katana_headless
                if service.katana_headless is not None
                else repo.katana_headless
            ),
            "max_duration": self._CRAWL_MAX_DURATION,
        }
        if headers:
            kwargs["headers"] = headers

        return [
            ExecutionPass(
                label_suffix=repo.name,
                kwargs=kwargs,
            )
        ]
