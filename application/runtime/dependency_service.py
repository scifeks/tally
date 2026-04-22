from collections.abc import Sequence

from domain.runtime.models import RuntimeDependencyStatus
from domain.runtime.probe import RuntimeDependencyProbe


class RuntimeDependencyService:
    def __init__(self, probes: Sequence[RuntimeDependencyProbe]) -> None:
        self._probes = list(probes)
        self._cache: list[RuntimeDependencyStatus] = []
        self.refresh()

    def refresh(self) -> None:
        self._cache = [p.probe() for p in self._probes]

    def statuses(self) -> list[RuntimeDependencyStatus]:
        return list(self._cache)

    def get(self, name: str) -> RuntimeDependencyStatus | None:
        for status in self._cache:
            if status.name == name:
                return status
        return None

    def is_installed(self, name: str) -> bool:
        status = self.get(name)
        return status is not None and status.installed
