"""Reset process-scoped state between scan runs."""

from infrastructure.tools.wrappers.utils.install_fallback import (
    reset_attempted as _reset_lockfile,
)
from infrastructure.tools.wrappers.utils.pip_deps import (
    reset_attempted as _reset_pip,
)


def reset_scan_scoped_state() -> None:
    """Clear dedup sets so SCA tools re-attempt on each scan."""
    _reset_lockfile()
    _reset_pip()
