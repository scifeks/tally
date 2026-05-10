"""Per-project Docker Compose file generation for triage agents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import yaml

from application.triage.container import TRIAGE_IMAGE_TAG
from application.triage.credentials import (
    ClaudeAuthMode,
    ClaudeCredentials,
    OpenCodeCredentials,
    resolve_claude_credentials,
)
from core.config.manager import ConfigManager

if TYPE_CHECKING:
    from application.ports.triage_compose import TriageComposePort

COMPOSE_RELATIVE_PATH = Path("docker/triage-agent/docker-compose.yaml")
PROXY_CONFIG_DIR = Path("docker/triage-agent")
PROXY_PORT = 8888

_LOCALHOST_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class ComposeGenerationError(RuntimeError):
    """Raised when compose file generation fails."""


def resolve_egress_target(
    provider: str,
    api_provider_url: str,
) -> tuple[str, int]:
    """Returns (host, port) for the proxy allowlist.

    Claude targets api.anthropic.com:443. OpenCode targets
    the configured inference endpoint parsed from the provider URL.
    """
    if provider == "claude":
        return ("api.anthropic.com", 443)

    if not api_provider_url:
        raise ComposeGenerationError(
            "triage_inference base_url must be set in "
            "config/global.json for network sandboxing."
        )
    parsed = urlparse(api_provider_url)
    if not parsed.hostname:
        raise ComposeGenerationError(
            f"Cannot parse hostname from opencode.api_provider: {api_provider_url}"
        )
    default_port = 443 if parsed.scheme == "https" else 80
    port = parsed.port or default_port
    return (parsed.hostname, port)


def _dockerize_url(url: str) -> str:
    """Rewrites localhost URLs to host.docker.internal.

    Inside a Docker container, localhost refers to the
    container's own loopback. This rewrites to the special
    Docker hostname that resolves to the host machine.
    Intended for inference endpoints that bind to localhost
    on the host but must be reached from inside the container.
    """
    parsed = urlparse(url)
    if parsed.hostname not in _LOCALHOST_HOSTS:
        return url
    port = parsed.port
    new_host = "host.docker.internal"
    if port:
        new_netloc = f"{new_host}:{port}"
    else:
        new_netloc = new_host
    return urlunparse(parsed._replace(netloc=new_netloc))


def build_proxy_config(connect_ports: list[int]) -> str:
    """Generates tinyproxy.conf content.

    Deduplicates ports before writing ConnectPort directives
    (a port only needs one directive even if requested multiple times).
    """
    port_lines = "\n".join(f"ConnectPort {p}" for p in sorted(set(connect_ports)))
    return (
        f"Port {PROXY_PORT}\n"
        f"Listen 0.0.0.0\n"
        f'LogFile "/dev/stdout"\n'
        f'PidFile "/run/tinyproxy.pid"\n'
        f"MaxClients 10\n"
        f"FilterDefaultDeny Yes\n"
        f'Filter "/etc/tinyproxy/filter"\n'
        f"FilterURLs Off\n"
        f"FilterExtended On\n"
        f"{port_lines}\n"
    )


def build_proxy_filter(allowed_hosts: list[str]) -> str:
    """Generates tinyproxy filter file content.

    Each host becomes a regex line anchored with ^ and $.
    Dots are escaped for literal matching. Anchoring ensures
    exact hostname matching and prevents overly permissive
    regexes (e.g., 'api.anthropic' would match 'api.anthropic-internal'
    without anchors, creating a security gap).
    """
    lines: list[str] = []
    for host in allowed_hosts:
        escaped = re.escape(host)
        lines.append(f"^{escaped}$")
    return "\n".join(lines) + "\n"


def build_opencode_config(
    *,
    provider_name: str,
    base_url: str,
    model: str,
) -> str:
    """Generates the opencode.json config with provider and permissions."""
    import json

    config: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            provider_name: {
                "npm": "@ai-sdk/openai-compatible",
                "name": provider_name,
                "options": {
                    "baseURL": base_url.rstrip("/") + "/v1",
                },
                "models": {
                    model: {"name": model},
                },
            },
        },
        "permission": {
            "edit": "deny",
            "bash": {"*": "deny"},
            "webfetch": "deny",
            "read": {"*": "allow"},
            "write": {"*": "deny"},
        },
    }
    return json.dumps(config, indent=2) + "\n"


def build_compose_dict(
    *,
    repo_paths: dict[str, Path],
    claude_creds: ClaudeCredentials,
    opencode_creds: OpenCodeCredentials,
    image_tag: str,
    proxy_config_path: Path,
    proxy_filter_path: Path,
    oauth_identity_path: Path | None = None,
    oauth_credentials_path: Path | None = None,
    opencode_config_path: Path | None = None,
) -> dict[str, Any]:
    """Builds the compose file structure as a dict.

    Pure function with no I/O.
    """
    volumes: list[dict[str, Any]] = []

    for name, host_path in sorted(repo_paths.items()):
        volumes.append(
            {
                "type": "bind",
                "source": str(host_path),
                "target": f"/workspace/repos/{name}",
            }
        )

    volumes.append({"type": "tmpfs", "target": "/tmp"})
    volumes.append(
        {
            "type": "tmpfs",
            "target": "/home/agent/.claude",
        }
    )
    for oc_dir in (
        "/home/agent/.opencode",
        "/home/agent/.local/share/opencode",
        "/home/agent/.local/state/opencode",
        "/home/agent/.cache/opencode",
        "/home/agent/.config/opencode",
    ):
        volumes.append(
            {
                "type": "tmpfs",
                "target": oc_dir,
                "tmpfs": {"mode": 0o1777},
            }
        )

    if oauth_identity_path is not None:
        volumes.append(
            {
                "type": "bind",
                "source": str(oauth_identity_path),
                "target": "/home/agent/.claude.json",
                "read_only": True,
            }
        )

    if oauth_credentials_path is not None:
        volumes.append(
            {
                "type": "bind",
                "source": str(oauth_credentials_path),
                "target": ("/home/agent/.claude/.credentials.json"),
                "read_only": True,
            }
        )

    if opencode_config_path is not None:
        volumes.append(
            {
                "type": "bind",
                "source": str(opencode_config_path),
                "target": "/etc/opencode/opencode.json",
                "read_only": True,
            }
        )

    proxy_url = f"http://triage-proxy:{PROXY_PORT}"
    environment: dict[str, str] = {
        "HTTP_PROXY": proxy_url,
        "HTTPS_PROXY": proxy_url,
    }

    if claude_creds.mode is ClaudeAuthMode.API_KEY:
        environment["ANTHROPIC_API_KEY"] = claude_creds.api_key

    if opencode_creds.api_key:
        environment["OPENCODE_API_KEY"] = opencode_creds.api_key
    if opencode_creds.api_provider:
        environment["OPENCODE_API_PROVIDER"] = opencode_creds.api_provider
        environment["OLLAMA_HOST"] = opencode_creds.api_provider

    agent_service: dict[str, Any] = {
        "image": image_tag,
        "user": "agent",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "command": ["sleep", "infinity"],
        "networks": ["triage-internal"],
        "depends_on": {
            "triage-proxy": {"condition": "service_started"},
        },
        "volumes": volumes,
        "environment": environment,
    }

    proxy_service: dict[str, Any] = {
        "image": image_tag,
        "user": "agent",
        "read_only": True,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "command": [
            "tinyproxy",
            "-d",
            "-c",
            "/etc/tinyproxy/tinyproxy.conf",
        ],
        "networks": ["triage-internal", "triage-external"],
        "extra_hosts": ["host.docker.internal:host-gateway"],
        "volumes": [
            {
                "type": "tmpfs",
                "target": "/run",
                "tmpfs": {"mode": 0o1777},
            },
            {
                "type": "bind",
                "source": str(proxy_config_path),
                "target": "/etc/tinyproxy/tinyproxy.conf",
                "read_only": True,
            },
            {
                "type": "bind",
                "source": str(proxy_filter_path),
                "target": "/etc/tinyproxy/filter",
                "read_only": True,
            },
        ],
    }

    return {
        "services": {
            "triage-agent": agent_service,
            "triage-proxy": proxy_service,
        },
        "networks": {
            "triage-internal": {"internal": True},
            "triage-external": {},
        },
    }


def _resolve_compose_port() -> TriageComposePort:
    from infrastructure.docker.triage_compose import (
        DockerTriageCompose,
    )

    return DockerTriageCompose()


def generate_triage_compose(
    app_root: Path,
    repo_paths: dict[str, Path],
    *,
    provider: str,
    base_url: str = "",
    model: str = "",
) -> Path:
    """Resolves credentials, validates OAuth files, generates
    and writes the compose file and proxy config. Returns the
    compose file path.

    ``provider`` is the provider name from ``triage_inference``
    (e.g. ``ollama``, ``llama_cpp``, ``claude``). For non-Claude
    providers, ``base_url`` and ``model`` are the merged values
    from the resolved triage config.
    """
    app_root = app_root.resolve()
    cfg = ConfigManager(str(app_root)).global_config
    claude_creds = resolve_claude_credentials(cfg.claude)

    is_claude = provider == "claude"
    api_provider_url = "" if is_claude else base_url
    opencode_creds = OpenCodeCredentials(
        api_key="",
        api_provider=api_provider_url,
        model=model,
    )

    oauth_identity: Path | None = None
    oauth_credentials: Path | None = None

    if is_claude and claude_creds.mode is ClaudeAuthMode.OAUTH:
        home = Path.home()
        oauth_identity = home / ".claude.json"
        oauth_credentials = home / ".claude" / ".credentials.json"
        _validate_oauth_file(oauth_identity)
        _validate_oauth_file(oauth_credentials)

    egress_host, egress_port = resolve_egress_target(provider, api_provider_url)

    if not is_claude and api_provider_url:
        rewritten = _dockerize_url(api_provider_url)
        if rewritten != api_provider_url:
            opencode_creds = OpenCodeCredentials(
                api_key="",
                api_provider=rewritten,
                model=model,
            )
            rewritten_host = urlparse(rewritten).hostname
            if rewritten_host:
                egress_host = rewritten_host

    connect_ports = [443]
    if egress_port != 443:
        connect_ports.append(egress_port)

    proxy_config_content = build_proxy_config(connect_ports)

    if is_claude:
        allowed_hosts = ["api.anthropic.com"]
    else:
        allowed_hosts = [egress_host]
    proxy_filter_content = build_proxy_filter(allowed_hosts)

    proxy_config_path = app_root / PROXY_CONFIG_DIR / "tinyproxy.conf"
    proxy_filter_path = app_root / PROXY_CONFIG_DIR / "filter"

    oc_config_path: Path | None = None
    oc_config_content: str = ""
    if not is_claude and model:
        oc_config_content = build_opencode_config(
            provider_name=provider,
            base_url=opencode_creds.api_provider,
            model=model,
        )
        oc_config_path = app_root / PROXY_CONFIG_DIR / "opencode.json"

    compose_dict = build_compose_dict(
        repo_paths=repo_paths,
        claude_creds=claude_creds,
        opencode_creds=opencode_creds,
        image_tag=TRIAGE_IMAGE_TAG,
        proxy_config_path=proxy_config_path,
        proxy_filter_path=proxy_filter_path,
        oauth_identity_path=oauth_identity,
        oauth_credentials_path=oauth_credentials,
        opencode_config_path=oc_config_path,
    )

    content = yaml.dump(
        compose_dict,
        default_flow_style=False,
        sort_keys=False,
    )
    compose_path = app_root / COMPOSE_RELATIVE_PATH
    port = _resolve_compose_port()
    port.write_compose_file(content, compose_path)
    port.write_compose_file(proxy_config_content, proxy_config_path)
    port.write_compose_file(proxy_filter_content, proxy_filter_path)
    if oc_config_path is not None:
        port.write_compose_file(oc_config_content, oc_config_path)
    return compose_path


def _validate_oauth_file(path: Path) -> None:
    if not path.exists():
        raise ComposeGenerationError(
            f"OAuth file not found: {path}. "
            "Run `claude` on the host to authenticate, "
            "or set `claude.api_key` in config/global.json."
        )
