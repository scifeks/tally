from domain.runtime.models import (
    RuntimeDependencyRequirement,
    RuntimeDependencyStatus,
)
from infrastructure.runtime._probe_runner import run_version_probe

_REQUIREMENT = RuntimeDependencyRequirement(
    name="docker",
    binary="docker",
    install_hint="https://docs.docker.com/get-docker/",
    required_for=("triage",),
)


class DockerProbe:
    @property
    def requirement(self) -> RuntimeDependencyRequirement:
        return _REQUIREMENT

    def probe(self) -> RuntimeDependencyStatus:
        return run_version_probe(_REQUIREMENT)
