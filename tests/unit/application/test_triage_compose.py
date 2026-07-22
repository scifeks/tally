"""Unit tests for application.triage.compose."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.triage.compose import (
    COMPOSE_RELATIVE_PATH,
    PROXY_PORT,
    ComposeGenerationError,
    _dockerize_url,
    build_claude_settings,
    build_compose_dict,
    build_opencode_config,
    build_proxy_config,
    build_proxy_filter,
    generate_triage_compose,
    resolve_egress_target,
)
from application.triage.credentials import (
    ClaudeAuthMode,
    ClaudeCredentials,
    OpenCodeCredentials,
)

_PORT_PATCH = "application.triage.compose._resolve_compose_port"
_CM_PATCH = "application.triage.compose.ConfigManager"
_HOME_PATCH = "application.triage.compose.Path.home"


def _claude_api_key(key: str = "sk-ant-test") -> ClaudeCredentials:
    return ClaudeCredentials(mode=ClaudeAuthMode.API_KEY, api_key=key)


def _claude_oauth() -> ClaudeCredentials:
    return ClaudeCredentials(mode=ClaudeAuthMode.OAUTH, api_key="")


def _opencode(
    key: str = "", provider: str = "", model: str = ""
) -> OpenCodeCredentials:
    return OpenCodeCredentials(api_key=key, api_provider=provider, model=model)


def _base_kwargs(**overrides):
    defaults = {
        "repo_paths": {},
        "claude_creds": _claude_oauth(),
        "opencode_creds": _opencode(),
        "image_tag": "tally/triage-agent",
        "proxy_config_path": Path("/tmp/test-proxy.conf"),
        "proxy_filter_path": Path("/tmp/test-filter"),
    }
    defaults.update(overrides)
    return defaults


def _service(result: dict) -> dict:
    return result["services"]["triage-agent"]


def _proxy(result: dict) -> dict:
    return result["services"]["triage-proxy"]


# -- resolve_egress_target -------------------------------------------


class TestResolveEgressTarget:
    def test_claude_returns_anthropic(self) -> None:
        host, port = resolve_egress_target("claude", "")
        assert host == "api.anthropic.com"
        assert port == 443

    def test_opencode_parses_host_and_port(self) -> None:
        host, port = resolve_egress_target("ollama", "http://myhost:11434/v1")
        assert host == "myhost"
        assert port == 11434

    def test_opencode_uses_default_http_port(self) -> None:
        host, port = resolve_egress_target("llama_cpp", "http://myhost/v1")
        assert host == "myhost"
        assert port == 80

    def test_opencode_uses_default_https_port(self) -> None:
        host, port = resolve_egress_target("ollama", "https://myhost/v1")
        assert host == "myhost"
        assert port == 443

    def test_opencode_raises_on_empty_url(self) -> None:
        with pytest.raises(
            ComposeGenerationError,
            match="base_url must be set",
        ):
            resolve_egress_target("ollama", "")

    def test_opencode_raises_on_unparseable_url(self) -> None:
        with pytest.raises(
            ComposeGenerationError,
            match="Cannot parse hostname",
        ):
            resolve_egress_target("ollama", "not-a-url")


# -- _dockerize_url --------------------------------------------------


class TestDockerizeUrl:
    def test_rewrites_localhost(self) -> None:
        result = _dockerize_url("http://localhost:11434/v1")
        assert "host.docker.internal" in result
        assert "localhost" not in result

    def test_rewrites_127_0_0_1(self) -> None:
        result = _dockerize_url("http://127.0.0.1:11434/v1")
        assert "host.docker.internal" in result
        assert "127.0.0.1" not in result

    def test_preserves_port_and_path(self) -> None:
        result = _dockerize_url("http://localhost:5000/custom/path")
        assert ":5000" in result
        assert "/custom/path" in result

    def test_leaves_remote_host_unchanged(self) -> None:
        url = "http://ollama.example.com:11434/v1"
        assert _dockerize_url(url) == url

    def test_leaves_non_localhost_ip_unchanged(self) -> None:
        url = "http://192.168.1.50:11434/v1"
        assert _dockerize_url(url) == url


# -- build_proxy_config ----------------------------------------------


class TestBuildProxyConfig:
    def test_includes_filter_default_deny(self) -> None:
        config = build_proxy_config([443])
        assert "FilterDefaultDeny Yes" in config

    def test_includes_connect_port(self) -> None:
        config = build_proxy_config([443])
        assert "ConnectPort 443" in config

    def test_includes_multiple_connect_ports(self) -> None:
        config = build_proxy_config([443, 11434])
        assert "ConnectPort 443" in config
        assert "ConnectPort 11434" in config

    def test_deduplicates_ports(self) -> None:
        config = build_proxy_config([443, 443])
        assert config.count("ConnectPort 443") == 1

    def test_includes_listen_port(self) -> None:
        config = build_proxy_config([443])
        assert f"Port {PROXY_PORT}" in config


# -- build_proxy_filter ----------------------------------------------


class TestBuildProxyFilter:
    def test_escapes_dots_in_hostname(self) -> None:
        content = build_proxy_filter(["api.anthropic.com"])
        assert r"api\.anthropic\.com" in content

    def test_anchors_with_caret_and_dollar(self) -> None:
        content = build_proxy_filter(["myhost"])
        assert "^myhost$" in content

    def test_multiple_hosts(self) -> None:
        content = build_proxy_filter(["api.anthropic.com", "host.docker.internal"])
        assert r"api\.anthropic\.com" in content
        assert r"host\.docker\.internal" in content


# -- build_opencode_config -------------------------------------------


class TestBuildOpenCodeConfig:
    def test_uses_provider_name_as_key(self) -> None:
        import json

        content = build_opencode_config(
            provider_name="llama_cpp",
            base_url="http://localhost:8080",
            model="qwen3:14b",
        )
        cfg = json.loads(content)
        assert "llama_cpp" in cfg["provider"]
        assert cfg["provider"]["llama_cpp"]["name"] == "llama_cpp"

    def test_appends_v1_to_base_url(self) -> None:
        import json

        content = build_opencode_config(
            provider_name="ollama",
            base_url="http://localhost:11434",
            model="gemma3:27b",
        )
        cfg = json.loads(content)
        options = cfg["provider"]["ollama"]["options"]
        assert options["baseURL"] == "http://localhost:11434/v1"

    def test_includes_model_in_registry(self) -> None:
        import json

        content = build_opencode_config(
            provider_name="ollama",
            base_url="http://localhost:11434",
            model="gemma3:27b",
        )
        cfg = json.loads(content)
        models = cfg["provider"]["ollama"]["models"]
        assert "gemma3:27b" in models

    def test_includes_permissions(self) -> None:
        import json

        content = build_opencode_config(
            provider_name="ollama",
            base_url="http://localhost:11434",
            model="gemma3:27b",
        )
        cfg = json.loads(content)
        assert cfg["permission"]["edit"] == "deny"


# -- build_claude_settings -------------------------------------------


class TestBuildClaudeSettings:
    def test_produces_valid_json(self) -> None:
        import json

        content = build_claude_settings("/home/agent/.claude/hooks/scope-guard.sh")
        cfg = json.loads(content)
        assert "hooks" in cfg

    def test_pre_tool_use_hook_targets_read_grep_glob(
        self,
    ) -> None:
        import json

        content = build_claude_settings("/home/agent/.claude/hooks/scope-guard.sh")
        cfg = json.loads(content)
        entry = cfg["hooks"]["PreToolUse"][0]
        assert entry["matcher"] == "Read|Grep|Glob"

    def test_hook_command_matches_input_path(self) -> None:
        import json

        content = build_claude_settings("/custom/path.sh")
        cfg = json.loads(content)
        hook = cfg["hooks"]["PreToolUse"][0]["hooks"][0]
        assert hook["type"] == "command"
        assert hook["command"] == "/custom/path.sh"


# -- build_compose_dict ----------------------------------------------


class TestBuildComposeDict:
    def test_single_repo_mounts_at_workspace_repos_name(
        self,
    ) -> None:
        result = build_compose_dict(
            **_base_kwargs(repo_paths={"myrepo": Path("/host/myrepo")})
        )
        volumes = _service(result)["volumes"]
        bind_mounts = [v for v in volumes if v.get("type") == "bind"]
        assert len(bind_mounts) == 1
        assert bind_mounts[0]["source"] == "/host/myrepo"
        assert bind_mounts[0]["target"] == "/workspace/repos/myrepo"

    def test_multiple_repos_each_mounted(self) -> None:
        repos = {
            "alpha": Path("/repos/alpha"),
            "beta": Path("/repos/beta"),
        }
        result = build_compose_dict(**_base_kwargs(repo_paths=repos))
        volumes = _service(result)["volumes"]
        bind_targets = [v["target"] for v in volumes if v.get("type") == "bind"]
        assert "/workspace/repos/alpha" in bind_targets
        assert "/workspace/repos/beta" in bind_targets

    def test_empty_repos_produces_no_bind_mounts(
        self,
    ) -> None:
        result = build_compose_dict(**_base_kwargs(repo_paths={}))
        volumes = _service(result)["volumes"]
        bind_mounts = [v for v in volumes if v.get("type") == "bind"]
        assert bind_mounts == []

    def test_tmpfs_for_tmp_and_runtime_dirs(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        volumes = _service(result)["volumes"]
        tmpfs_targets = [v["target"] for v in volumes if v.get("type") == "tmpfs"]
        assert "/tmp" in tmpfs_targets
        assert "/home/agent/.claude" in tmpfs_targets
        assert "/home/agent/.opencode" in tmpfs_targets
        assert "/home/agent/.local/share/opencode" in tmpfs_targets
        assert "/home/agent/.local/state/opencode" in tmpfs_targets
        assert "/home/agent/.cache/opencode" in tmpfs_targets
        assert "/home/agent/.config/opencode" in tmpfs_targets

    def test_claude_api_key_mode_sets_env_var(self) -> None:
        result = build_compose_dict(
            **_base_kwargs(claude_creds=_claude_api_key("sk-key-123"))
        )
        env = _service(result)["environment"]
        assert env["ANTHROPIC_API_KEY"] == "sk-key-123"

    def test_claude_api_key_mode_no_oauth_mounts(
        self,
    ) -> None:
        result = build_compose_dict(**_base_kwargs(claude_creds=_claude_api_key()))
        volumes = _service(result)["volumes"]
        targets = [v.get("target", "") for v in volumes]
        assert "/home/agent/.claude.json" not in targets
        assert "/home/agent/.claude/.credentials.json" not in targets

    def test_claude_oauth_mode_mounts_credential_files(
        self,
    ) -> None:
        result = build_compose_dict(
            **_base_kwargs(
                claude_creds=_claude_oauth(),
                oauth_identity_path=Path("/home/user/.claude.json"),
                oauth_credentials_path=Path("/home/user/.claude/.credentials.json"),
            )
        )
        volumes = _service(result)["volumes"]
        oauth_binds = [
            v for v in volumes if v.get("type") == "bind" and v.get("read_only") is True
        ]
        assert len(oauth_binds) == 2
        targets = {v["target"] for v in oauth_binds}
        assert "/home/agent/.claude.json" in targets
        assert "/home/agent/.claude/.credentials.json" in targets

    def test_claude_oauth_mode_no_api_key_env(self) -> None:
        result = build_compose_dict(**_base_kwargs(claude_creds=_claude_oauth()))
        env = _service(result)["environment"]
        assert "ANTHROPIC_API_KEY" not in env

    def test_opencode_env_vars_when_configured(
        self,
    ) -> None:
        result = build_compose_dict(
            **_base_kwargs(
                opencode_creds=_opencode(
                    key="oc-key",
                    provider="http://localhost:11434/v1",
                )
            )
        )
        env = _service(result)["environment"]
        assert env["OPENCODE_API_KEY"] == "oc-key"
        assert env["OPENCODE_API_PROVIDER"] == "http://localhost:11434/v1"

    def test_opencode_env_vars_omitted_when_empty(
        self,
    ) -> None:
        result = build_compose_dict(**_base_kwargs(opencode_creds=_opencode()))
        env = _service(result).get("environment", {})
        assert "OPENCODE_API_KEY" not in env
        assert "OPENCODE_API_PROVIDER" not in env

    def test_container_hardening_flags(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        svc = _service(result)
        assert svc["read_only"] is True
        assert svc["cap_drop"] == ["ALL"]
        assert svc["security_opt"] == ["no-new-privileges:true"]
        assert svc["user"] == "agent"

    def test_image_tag_matches_input(self) -> None:
        result = build_compose_dict(**_base_kwargs(image_tag="custom/image:v2"))
        assert _service(result)["image"] == "custom/image:v2"

    def test_agent_has_keepalive_command(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        assert _service(result)["command"] == [
            "sleep",
            "infinity",
        ]

    def test_no_backend_env_when_no_api_keys(self) -> None:
        result = build_compose_dict(
            **_base_kwargs(
                claude_creds=_claude_oauth(),
                opencode_creds=_opencode(),
            )
        )
        env = _service(result)["environment"]
        assert "ANTHROPIC_API_KEY" not in env
        assert "OPENCODE_API_KEY" not in env
        assert "OPENCODE_API_PROVIDER" not in env

    # -- proxy service tests -----------------------------------------

    def test_proxy_service_exists(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        assert "triage-proxy" in result["services"]

    def test_agent_on_internal_network_only(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        assert _service(result)["networks"] == ["triage-internal"]

    def test_agent_depends_on_proxy(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        deps = _service(result)["depends_on"]
        assert "triage-proxy" in deps

    def test_agent_has_proxy_env_vars(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        env = _service(result)["environment"]
        assert "HTTP_PROXY" in env
        assert "HTTPS_PROXY" in env
        assert f"triage-proxy:{PROXY_PORT}" in env["HTTP_PROXY"]
        assert env["HTTP_PROXY"] == env["HTTPS_PROXY"]

    def test_claude_settings_mounted_when_provided(
        self,
    ) -> None:
        result = build_compose_dict(
            **_base_kwargs(
                claude_settings_path=Path("/app/claude-settings.json"),
            )
        )
        volumes = _service(result)["volumes"]
        settings_mount = [
            v for v in volumes if v.get("target") == "/home/agent/.claude/settings.json"
        ]
        assert len(settings_mount) == 1
        assert settings_mount[0]["source"] == "/app/claude-settings.json"
        assert settings_mount[0]["read_only"] is True

    def test_hook_script_mounted_when_provided(
        self,
    ) -> None:
        result = build_compose_dict(
            **_base_kwargs(
                claude_hook_script_path=Path("/app/hooks/scope-guard.sh"),
            )
        )
        volumes = _service(result)["volumes"]
        hook_mount = [v for v in volumes if "scope-guard" in v.get("target", "")]
        assert len(hook_mount) == 1
        assert hook_mount[0]["read_only"] is True

    def test_no_settings_mount_when_path_is_none(
        self,
    ) -> None:
        result = build_compose_dict(**_base_kwargs())
        volumes = _service(result)["volumes"]
        targets = [v.get("target", "") for v in volumes]
        assert "/home/agent/.claude/settings.json" not in targets

    def test_proxy_on_both_networks(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        networks = _proxy(result)["networks"]
        assert "triage-internal" in networks
        assert "triage-external" in networks

    def test_proxy_hardening_flags(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        svc = _proxy(result)
        assert svc["read_only"] is True
        assert svc["cap_drop"] == ["ALL"]
        assert svc["security_opt"] == ["no-new-privileges:true"]

    def test_proxy_runs_tinyproxy(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        cmd = _proxy(result)["command"]
        assert cmd[0] == "tinyproxy"
        assert "-d" in cmd

    def test_proxy_has_extra_hosts(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        hosts = _proxy(result)["extra_hosts"]
        assert "host.docker.internal:host-gateway" in hosts

    def test_proxy_mounts_config_files(self) -> None:
        cfg_path = Path("/app/docker/triage-agent/tinyproxy.conf")
        flt_path = Path("/app/docker/triage-agent/filter")
        result = build_compose_dict(
            **_base_kwargs(
                proxy_config_path=cfg_path,
                proxy_filter_path=flt_path,
            )
        )
        volumes = _proxy(result)["volumes"]
        sources = {v.get("source") for v in volumes if "source" in v}
        assert str(cfg_path) in sources
        assert str(flt_path) in sources

    def test_internal_network_is_internal(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        assert result["networks"]["triage-internal"]["internal"] is True

    def test_external_network_exists(self) -> None:
        result = build_compose_dict(**_base_kwargs())
        assert "triage-external" in result["networks"]


# -- generate_triage_compose -----------------------------------------


class TestGenerateTriageCompose:
    def _mock_config(self, api_key: str = "") -> MagicMock:
        mock_cm = MagicMock()
        mock_cm.return_value.global_config.claude = (
            MagicMock(api_key=api_key) if api_key else None
        )
        return mock_cm

    def test_returns_compose_path(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            result = generate_triage_compose(tmp_path, {}, provider="claude")
        assert result == tmp_path / COMPOSE_RELATIVE_PATH

    def test_writes_compose_and_proxy_files(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")
        assert mock_port.write_compose_file.call_count == 4
        paths_written = {
            call[0][1].name for call in mock_port.write_compose_file.call_args_list
        }
        assert "docker-compose.yaml" in paths_written
        assert "tinyproxy.conf" in paths_written
        assert "filter" in paths_written
        assert "claude-settings.json" in paths_written

    def test_claude_filter_includes_anthropic(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")
        filter_call = [
            c
            for c in mock_port.write_compose_file.call_args_list
            if c[0][1].name == "filter"
        ][0]
        filter_content = filter_call[0][0]
        assert r"^api\.anthropic\.com$" in filter_content

    def test_ollama_filter_includes_host(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config()),
        ):
            generate_triage_compose(
                tmp_path,
                {},
                provider="ollama",
                base_url="http://ollama.local:11434/v1",
                model="testmodel",
            )
        filter_call = [
            c
            for c in mock_port.write_compose_file.call_args_list
            if c[0][1].name == "filter"
        ][0]
        filter_content = filter_call[0][0]
        assert r"^ollama\.local$" in filter_content

    def test_localhost_rewritten_in_compose(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config()),
        ):
            generate_triage_compose(
                tmp_path,
                {},
                provider="llama_cpp",
                base_url="http://localhost:11434/v1",
                model="testmodel",
            )
        compose_call = [
            c
            for c in mock_port.write_compose_file.call_args_list
            if c[0][1].name == "docker-compose.yaml"
        ][0]
        yaml_content = compose_call[0][0]
        assert "host.docker.internal" in yaml_content
        assert "http://localhost:11434" not in yaml_content
        assert "11434" in yaml_content

    def test_claude_oauth_validates_identity_file(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        creds_dir = fake_home / ".claude"
        creds_dir.mkdir()
        (creds_dir / ".credentials.json").write_text("{}")

        with (
            patch(_PORT_PATCH, return_value=MagicMock()),
            patch(_CM_PATCH, self._mock_config()),
            patch(_HOME_PATCH, return_value=fake_home),
            pytest.raises(
                ComposeGenerationError,
                match="OAuth file not found.*\\.claude\\.json",
            ),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")

    def test_claude_oauth_validates_credentials_file(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        (fake_home / ".claude.json").write_text("{}")

        with (
            patch(_PORT_PATCH, return_value=MagicMock()),
            patch(_CM_PATCH, self._mock_config()),
            patch(_HOME_PATCH, return_value=fake_home),
            pytest.raises(
                ComposeGenerationError,
                match="OAuth file not found.*\\.credentials\\.json",
            ),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")

    def test_claude_api_key_skips_oauth_validation(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")
        assert mock_port.write_compose_file.call_count == 4

    def test_non_claude_provider_writes_opencode_config(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config()),
        ):
            generate_triage_compose(
                tmp_path,
                {},
                provider="ollama",
                base_url="http://localhost:11434",
                model="testmodel",
            )
        assert mock_port.write_compose_file.call_count == 5
        paths_written = {
            call[0][1].name for call in mock_port.write_compose_file.call_args_list
        }
        assert "opencode.json" in paths_written
        assert "claude-settings.json" in paths_written

    def test_relative_app_root_produces_absolute_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "global.json").write_text("{}")

        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            generate_triage_compose(Path("."), {}, provider="claude")
        compose_call = [
            c
            for c in mock_port.write_compose_file.call_args_list
            if c[0][1].name == "docker-compose.yaml"
        ][0]
        yaml_content = compose_call[0][0]
        assert "docker/triage-agent/docker/triage-agent" not in yaml_content

    def test_writes_claude_settings_file(self, tmp_path: Path) -> None:
        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")
        paths_written = {
            call[0][1].name for call in mock_port.write_compose_file.call_args_list
        }
        assert "claude-settings.json" in paths_written

    def test_claude_settings_contains_hook_config(self, tmp_path: Path) -> None:
        import json

        mock_port = MagicMock()
        with (
            patch(_PORT_PATCH, return_value=mock_port),
            patch(_CM_PATCH, self._mock_config(api_key="sk-x")),
        ):
            generate_triage_compose(tmp_path, {}, provider="claude")
        settings_call = [
            c
            for c in mock_port.write_compose_file.call_args_list
            if c[0][1].name == "claude-settings.json"
        ][0]
        cfg = json.loads(settings_call[0][0])
        assert cfg["hooks"]["PreToolUse"][0]["matcher"] == ("Read|Grep|Glob")
