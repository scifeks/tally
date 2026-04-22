from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeDependencyRequirement:
    name: str
    binary: str
    install_hint: str
    required_for: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeDependencyStatus:
    name: str
    installed: bool
    binary_path: str | None
    version: str | None
    install_hint: str
    required_for: tuple[str, ...]
    error: str | None
