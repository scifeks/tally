"""Interactive setup for nmap scan targets."""

from __future__ import annotations

from infrastructure.tools.nmap_utils import _is_valid_host


def _prompt(message: str, default: str = "") -> str:
    """Prompt user and return stripped input, falling back to default."""
    suffix = f" [{default}]" if default else ""
    raw = input(f"{message}{suffix}: ").strip()
    return raw or default


def _interview_hosts(prompt_label: str) -> list[str]:
    """Prompt for comma-separated IPs/CIDRs, validate each, return list."""
    while True:
        raw = input(f"  {prompt_label}: ").strip()
        if not raw:
            return []
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        invalid = [p for p in parts if not _is_valid_host(p)]
        if invalid:
            print(f"  Invalid IPs/CIDRs: {', '.join(invalid)}. Try again.")
            continue
        return parts


def interview_nmap_config(
    project_name: str,
    base_path: str,
    existing: object = None,
) -> None:
    """Interactive interview to create or edit nmap_hosts.json.

    Args:
        project_name: Active project name.
        base_path: Application base path for ConfigManager.
        existing: NmapHostsConfig instance for edit mode, or None for add mode.
    """
    if existing is None:
        _interview_add_mode(project_name, base_path)
    else:
        _interview_edit_mode(project_name, base_path, existing)  # type: ignore[arg-type]


def _interview_add_mode(project_name: str, base_path: str) -> None:
    from core.config.manager import ConfigManager
    from core.config.schemas import NmapProfile

    print(f"\nConfiguring nmap scan targets for project '{project_name}'...")

    answer = _prompt("\nAdd named scan targets? [y/N]", default="N").lower()
    if answer not in ("y", "yes"):
        return

    profiles: dict[str, NmapProfile] = {}
    scan_idx = 1
    while True:
        print(f"\nScan #{scan_idx}:")
        while True:
            name = input("  Name: ").strip()
            if not name:
                print("  Name is required.")
                continue
            if name in profiles:
                print(f"  Name '{name}' already used. Choose a different name.")
                continue
            break

        hosts = _interview_hosts("Hosts (comma-separated IPs/CIDRs)")
        if not hosts:
            print("  At least one host is required.")
            continue

        nmap_args = _prompt(
            "  Nmap args (blank for default -sV -sC -O)", default="-sV -sC -O"
        )

        profiles[name] = NmapProfile(hosts=hosts, nmap_args=nmap_args)
        scan_idx += 1

        again = _prompt("\n  Add another scan target? [y/N]", default="N").lower()
        if again not in ("y", "yes"):
            break

    excluded: list[str] = []
    excl_answer = _prompt("\nAdd exclusion list? [y/N]", default="N").lower()
    if excl_answer in ("y", "yes"):
        excluded = _interview_hosts("Excluded hosts/CIDRs (comma-separated)")

    ConfigManager(base_path).save_nmap_hosts(project_name, profiles, excluded)
    print("\n✓ Nmap config saved.")


def _interview_edit_mode(project_name: str, base_path: str, existing: object) -> None:
    from core.config.manager import ConfigManager
    from core.config.schemas import NmapHostsConfig, NmapProfile

    cfg: NmapHostsConfig = existing  # type: ignore[assignment]
    print(
        f"\nEditing nmap scan targets for project '{project_name}'"
        " (press Enter to keep)..."
    )

    updated_profiles: dict[str, NmapProfile] = {}

    for scan_name, profile in cfg.profiles.items():
        print(f"\nNamed scan '{scan_name}':")
        current_hosts = ", ".join(profile.hosts)

        while True:
            raw_hosts = _prompt("  Hosts", default=current_hosts)
            parts = [p.strip() for p in raw_hosts.split(",") if p.strip()]
            invalid = [p for p in parts if not _is_valid_host(p)]
            if invalid:
                print(f"  Invalid IPs/CIDRs: {', '.join(invalid)}. Try again.")
                continue
            hosts = parts or profile.hosts
            break

        nmap_args = _prompt("  Nmap args", default=profile.nmap_args)
        keep = _prompt("  Keep this scan? [Y/n]", default="Y").lower()
        if keep not in ("n", "no"):
            updated_profiles[scan_name] = NmapProfile(hosts=hosts, nmap_args=nmap_args)

    # Add new scans
    add_new = _prompt("\nAdd a new scan target? [y/N]", default="N").lower()
    if add_new in ("y", "yes"):
        while True:
            while True:
                name = input("  Name: ").strip()
                if not name:
                    print("  Name is required.")
                    continue
                if name in updated_profiles:
                    print(f"  Name '{name}' already used.")
                    continue
                break

            hosts = _interview_hosts("  Hosts (comma-separated IPs/CIDRs)")
            if not hosts:
                print("  At least one host is required.")
                continue

            nmap_args = _prompt(
                "  Nmap args (blank for default -sV -sC -O)", default="-sV -sC -O"
            )
            updated_profiles[name] = NmapProfile(hosts=hosts, nmap_args=nmap_args)

            again = _prompt("\n  Add another? [y/N]", default="N").lower()
            if again not in ("y", "yes"):
                break

    # Exclusion list
    current_excl = ", ".join(cfg.excluded_networks) if cfg.excluded_networks else ""
    if current_excl:
        print("\nExclusion list:")
        raw_excl = _prompt("  Hosts/CIDRs", default=current_excl)
        parts = [p.strip() for p in raw_excl.split(",") if p.strip()]
        valid_excl = [p for p in parts if _is_valid_host(p)]
        keep_excl = _prompt("  Keep exclusion list? [Y/n]", default="Y").lower()
        excluded = valid_excl if keep_excl not in ("n", "no") else []
    else:
        excl_answer = _prompt("\nAdd exclusion list? [y/N]", default="N").lower()
        if excl_answer in ("y", "yes"):
            excluded = _interview_hosts("  Excluded hosts/CIDRs (comma-separated)")
        else:
            excluded = []

    ConfigManager(base_path).save_nmap_hosts(project_name, updated_profiles, excluded)
    print("\n✓ Nmap config saved.")
