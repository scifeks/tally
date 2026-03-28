"""Network utility helpers for nmap wrappers."""

from __future__ import annotations

import ipaddress


def _to_network(s: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    try:
        return ipaddress.ip_network(s, strict=False)
    except ValueError:
        return None


def _is_valid_host(s: str) -> bool:
    """Validate IP address or CIDR notation."""
    return _to_network(s) is not None


def check_exclusion_conflicts(hosts: list[str], excluded: list[str]) -> list[str]:
    """Return list of conflict descriptions for hosts that overlap excluded networks.

    Args:
        hosts: List of host IPs/CIDRs to check.
        excluded: List of excluded IPs/CIDRs.

    Returns:
        List of human-readable conflict strings, empty if no conflicts.
    """
    conflicts: list[str] = []
    excl_nets = [n for e in excluded if (n := _to_network(e)) is not None]
    for h in hosts:
        h_net = _to_network(h)
        if h_net is None:
            continue
        for e_net in excl_nets:
            if h_net.overlaps(e_net):
                conflicts.append(f"{h} overlaps with excluded {e_net}")
                break
    return conflicts
