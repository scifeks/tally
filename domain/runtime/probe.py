from typing import Protocol

from domain.runtime.models import RuntimeDependencyRequirement, RuntimeDependencyStatus


class RuntimeDependencyProbe(Protocol):
    @property
    def requirement(self) -> RuntimeDependencyRequirement: ...

    def probe(self) -> RuntimeDependencyStatus: ...
