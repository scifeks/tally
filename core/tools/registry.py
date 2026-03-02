from typing import Dict, List, Optional

from .base import ToolWrapper


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolWrapper] = {}

    def register(self, tool: ToolWrapper) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[ToolWrapper]:
        return self._tools.get(name)

    def get_tools_by_category(self, category: str) -> List[ToolWrapper]:
        return [t for t in self._tools.values() if t.category == category]

    def get_tools_by_scope(self, scope: str) -> List[ToolWrapper]:
        return [t for t in self._tools.values() if t.scope == scope]

    def list_all(self) -> List[ToolWrapper]:
        return list(self._tools.values())

    def check_availability(self) -> Dict[str, bool]:
        return {name: tool.check_available() for name, tool in self._tools.items()}


tool_registry = ToolRegistry()

from .wrappers.composer_audit import ComposerAuditWrapper  # noqa: E402
from .wrappers.gitleaks import GitleaksWrapper  # noqa: E402
from .wrappers.nmap import NmapWrapper  # noqa: E402
from .wrappers.npm_audit import NpmAuditWrapper  # noqa: E402
from .wrappers.osv_scanner import OSVScannerWrapper  # noqa: E402
from .wrappers.pip_audit import PipAuditWrapper  # noqa: E402
from .wrappers.semgrep import SemgrepWrapper  # noqa: E402
from .wrappers.zap import ZAPWrapper  # noqa: E402

tool_registry.register(NmapWrapper())
tool_registry.register(OSVScannerWrapper())
tool_registry.register(SemgrepWrapper())
tool_registry.register(PipAuditWrapper())
tool_registry.register(NpmAuditWrapper())
tool_registry.register(ComposerAuditWrapper())
tool_registry.register(GitleaksWrapper())
tool_registry.register(ZAPWrapper())
