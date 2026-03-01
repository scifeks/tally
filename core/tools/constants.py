from typing import Dict, List

SCAN_SEGMENTS: Dict[str, List[str]] = {
    'network': ['nmap'],
    'sast': ['semgrep'],
    'sca': ['osv-scanner', 'pip-audit', 'npm-audit', 'composer-audit'],
    'secrets': ['gitleaks'],
    'api': ['zap'],
}

SEVERITY_LEVELS: List[str] = ['low', 'medium', 'high', 'critical']
