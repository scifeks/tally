from domain.runtime.models import (
    RuntimeDependencyRequirement,
    RuntimeDependencyStatus,
)
from infrastructure.runtime._probe_runner import run_version_probe

_REQUIREMENT = RuntimeDependencyRequirement(
    name="opencode",
    binary="opencode",
    install_hint="See https://opencode.ai/docs/cli/",
    required_for=("triage",),
)


class OpenCodeProbe:
    @property
    def requirement(self) -> RuntimeDependencyRequirement:
        return _REQUIREMENT

    def probe(self) -> RuntimeDependencyStatus:
        return run_version_probe(_REQUIREMENT)
