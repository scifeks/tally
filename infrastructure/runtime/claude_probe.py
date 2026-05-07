from domain.runtime.models import (
    RuntimeDependencyRequirement,
    RuntimeDependencyStatus,
)
from infrastructure.runtime._probe_runner import run_version_probe

_REQUIREMENT = RuntimeDependencyRequirement(
    name="claude",
    binary="claude",
    install_hint="See https://code.claude.com/docs/en/quickstart",
    required_for=("triage",),
)


class ClaudeCodeProbe:
    @property
    def requirement(self) -> RuntimeDependencyRequirement:
        return _REQUIREMENT

    def probe(self) -> RuntimeDependencyStatus:
        return run_version_probe(_REQUIREMENT)
