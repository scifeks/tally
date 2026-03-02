"""OWASP ZAP wrapper for dynamic web application / API security testing."""
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import ToolWrapper
from ..parsers.zap_parser import parse_zap_json, parse_zap_json_string, parse_zap_xml

# Candidate binaries in preference order
_ZAP_CANDIDATES = ("zap.sh", "zap-cli", "zaproxy")


class ZAPWrapper(ToolWrapper):
    """Wrapper for OWASP ZAP quick-scan (DAST) mode.

    Quick-scan MVP: ``zap.sh -cmd -quickurl <url> -quickprogress -quickout <file>``

    Full active-scan (spider + active scan in daemon mode) is documented for a
    future enhancement but not implemented here.
    """

    def __init__(self) -> None:
        # Populated by check_available(); used by build_command()
        self._found_command: Optional[str] = None
        # Set by build_command(); read by parse_output()
        self._last_report_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # ToolWrapper abstract properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "zap"

    @property
    def command(self) -> str:
        return "zap.sh"

    @property
    def category(self) -> str:
        return "api"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def supported_languages(self) -> Optional[List[str]]:
        return None  # Tests running applications, not source code

    @property
    def description(self) -> str:
        return "OWASP ZAP dynamic web application security scanner"

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    def check_available(self) -> bool:
        """Return True if any ZAP binary variant is on PATH."""
        for candidate in _ZAP_CANDIDATES:
            if shutil.which(candidate) is not None:
                self._found_command = candidate
                return True
        self._found_command = None
        return False

    # ------------------------------------------------------------------
    # Command building
    # ------------------------------------------------------------------

    def build_command(self, **kwargs) -> List[str]:
        """Build the ZAP quick-scan argv list.

        Keyword Args:
            base_url (str): API base URL to scan. Required.
            endpoints (Dict[str, List[str]]): Endpoint map from the project's
                endpoint config.  Informational only in quick-scan mode — ZAP
                will spider from ``base_url`` automatically.
            api_type (str): ``"rest"`` or ``"graphql"`` (default: ``"rest"``).
                Reserved for future comprehensive-scan mode.
            auth_token (Optional[str]): Bearer token for authenticated targets.
                Reserved for future comprehensive-scan mode; ZAP quick-scan
                does not support per-request auth headers via CLI flags.
            output_file (Optional[str]): Filesystem path for the ZAP JSON
                report.  If omitted a temporary file is used.
        """
        base_url: Optional[str] = kwargs.get("base_url")
        if not base_url:
            raise ValueError("base_url is required for ZAP")

        output_file: Optional[str] = kwargs.get("output_file")
        if not output_file:
            output_file = str(
                Path(tempfile.gettempdir()) / f"zap_report_{os.getpid()}.json"
            )

        self._last_report_path = Path(output_file)

        zap_cmd = self._found_command or "zap.sh"

        return [
            zap_cmd, "-cmd",
            "-quickurl", base_url,
            "-quickprogress",
            "-quickout", output_file,
        ]

    # ------------------------------------------------------------------
    # Output parsing
    # ------------------------------------------------------------------

    def parse_output(self, output: str, files: Dict[str, Path]) -> Dict[str, Any]:
        """Parse ZAP scan output into structured data.

        ZAP writes its report to the file specified by ``-quickout`` rather
        than to stdout.  We therefore prefer the report file stored in
        ``_last_report_path``; the stdout capture saved by the executor (which
        contains progress messages only) is used as a last resort.
        """
        # 1. Report file written by ZAP itself
        if self._last_report_path is not None and self._last_report_path.exists():
            suffix = self._last_report_path.suffix.lower()
            if suffix == ".xml":
                return parse_zap_xml(self._last_report_path)
            return parse_zap_json(self._last_report_path)

        # 2. Stdout file saved by executor (may contain progress text, not JSON)
        stdout_path = files.get("stdout")
        if stdout_path is not None and stdout_path.exists():
            return parse_zap_json(stdout_path)

        # 3. Raw output string (fallback — unlikely to be valid JSON)
        return parse_zap_json_string(output)
