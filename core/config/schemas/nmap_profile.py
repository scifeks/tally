"""NmapProfile schema."""

from pydantic import BaseModel, Field


class NmapProfile(BaseModel):
    """Nmap scan profile configuration."""

    hosts: list[str] = Field(..., description="List of hosts/subnets to scan")
    nmap_args: str = Field(default="", description="Nmap arguments for this profile")
