"""NmapHostsConfig schema."""

from pydantic import BaseModel, Field

from .nmap_profile import NmapProfile


class NmapHostsConfig(BaseModel):
    """Full nmap_hosts.json configuration."""

    profiles: dict[str, NmapProfile] = Field(default_factory=dict)
    excluded_networks: list[str] = Field(default_factory=list)
