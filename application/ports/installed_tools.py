"""Port: query which tool wrappers are installed on the host system.

The installed-tools snapshot is captured once per process lifetime (typically
at REPL boot or web-server startup) and never re-probed. The data is
accurate at the moment the process starts; if the user installs or removes
a tool while the REPL is running, the port will not see it until the
process restarts. This is intentional; re-probing on every API request
would be slow, and re-probing on a schedule would create cache-coherence
problems with downstream UI gating.
"""

from __future__ import annotations

from typing import Protocol


class InstalledToolsPort(Protocol):
    """Query which tool wrappers have a usable binary on PATH."""

    def installed(self) -> frozenset[str]:
        """Return the set of tool names whose binary was probed at startup."""
        ...
