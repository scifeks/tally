SCAN_SEGMENTS: dict[str, list[str]] = {
    "network": ["nmap"],
    "sast": ["semgrep"],
    "sca": ["osv-scanner", "pip-audit", "npm-audit", "composer-audit"],
    "secrets": ["gitleaks"],
    "api": ["zap"],
}

SEVERITY_LEVELS: list[str] = ["low", "medium", "high", "critical"]
