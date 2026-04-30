"""Shared base class for the OWASP Noir endpoint-discovery wrapper.

Noir is a Crystal binary (``/usr/bin/noir``) that performs static analysis
on source code and emits discovered API endpoints as an OAS3 JSON document.
It is a **pre-DAST** step: its output feeds into ZAP via the
``-openapifile`` flag rather than being a vulnerability scanner itself.

Architecture note
-----------------
Because Noir writes its report to a file specified by ``-o`` (not to stdout),
the concrete ``NoirLocalTool`` subclass overrides ``parse_output`` exactly as
``GitleaksLocalTool`` does for its JSON report path.  The base class
``parse_output`` is a safe fallback that handles the stdout path in case
a future Docker wrapper captures output differently.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.project_paths import ProjectPaths
from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface
from infrastructure.tools.parsers.noir import (
    parse_noir_json,
    parse_noir_json_string,
)

# Mapping from tally Repository.languages values to Noir -t tech identifiers.
# Derived from `noir --list-techs` output (v0.25.1).
LANGUAGE_TO_NOIR_TECHS: dict[str, list[str]] = {
    "python": [
        "python_django",
        "python_fastapi",
        "python_flask",
        "python_sanic",
        "python_tornado",
    ],
    "php": [
        "php_pure",
        "php_laravel",
        "php_symfony",
    ],
    "javascript/typescript": [
        "js_express",
        "js_restify",
        "js_fastify",
        "js_koa",
        "js_nestjs",
    ],
    "node": [
        "js_express",
        "js_restify",
        "js_fastify",
        "js_koa",
        "js_nestjs",
    ],
    "ruby": [
        "ruby_hanami",
        "ruby_rails",
        "ruby_sinatra",
    ],
    "go": [
        "go_beego",
        "go_echo",
        "go_fasthttp",
        "go_fiber",
        "go_gin",
        "go_chi",
        "go_gozero",
        "go_mux",
    ],
    "java": [
        "java_armeria",
        "java_jsp",
        "java_spring",
        "java_vertx",
    ],
    "kotlin": [
        "kotlin_spring",
        "kotlin_ktor",
    ],
    "rust": [
        "rust_axum",
        "rust_rocket",
        "rust_actix_web",
        "rust_loco",
        "rust_rwf",
        "rust_tide",
        "rust_warp",
        "rust_gotham",
    ],
    "c#": [
        "cs_aspnet_mvc",
    ],
    "crystal": [
        "crystal_amber",
        "crystal_kemal",
        "crystal_lucky",
        "crystal_marten",
        "crystal_grip",
    ],
    "elixir": [
        "elixir_phoenix",
        "elixir_plug",
    ],
}


def _compute_noir_techs(repo_languages: list[str]) -> list[str]:
    """Compute a deduplicated list of Noir tech identifiers from repo languages."""
    techs: list[str] = []
    seen: set[str] = set()
    for lang in repo_languages:
        for tech in LANGUAGE_TO_NOIR_TECHS.get(lang.lower(), []):
            if tech not in seen:
                techs.append(tech)
                seen.add(tech)
    return techs


class BaseNoirTool(ToolInterface):
    """Base class for the Noir local wrapper."""

    _candidate_commands: list[str] = ["noir"]
    _command_entry_type: str = "repo"

    # ------------------------------------------------------------------
    # ToolInterface — identity
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "noir"

    @property
    def category(self) -> str:
        return "web"

    @property
    def scope(self) -> str:
        return "repository"

    @property
    def description(self) -> str:
        return (
            "OWASP Noir — attack surface detector that discovers API endpoints "
            "by static analysis and emits an OAS3 spec for downstream DAST."
        )

    @property
    def scan_segment(self) -> str:
        return "web"

    # ------------------------------------------------------------------
    # ToolInterface — behaviour flags
    # ------------------------------------------------------------------

    @property
    def skip(self) -> bool:
        # Noir produces endpoint *metadata*, not triage-able vulnerability
        # findings.  Rows are stored as informational records; triage is skipped.
        return True

    @property
    def is_discovery_tool(self) -> bool:
        return True

    @property
    def should_visualize(self) -> bool:
        """Noir findings are endpoint metadata, not triage-able findings."""
        return False

    @property
    def findings_exit_ok(self) -> bool:
        # Noir exits 0 regardless of how many endpoints it finds.
        return True

    @property
    def language_gates(self) -> list[str]:
        # Language-agnostic — scans any source tree.
        return []

    @property
    def requires_base_urls(self) -> bool:
        # Noir analyses source code; it does not need a live URL.
        return False

    @property
    def always_run(self) -> bool:
        return True

    @property
    def candidate_commands(self) -> list[str]:
        return self._candidate_commands

    @property
    def supported_languages(self) -> list[str] | None:
        return self.language_gates or None

    # ------------------------------------------------------------------
    # ToolInterface — parse + execute
    # ------------------------------------------------------------------

    def parse_output(self, output: str, files: dict[str, Path]) -> dict[str, Any]:
        """Parse Noir output.

        Prefers the saved stdout file (for wrappers that capture stdout);
        falls back to the raw output string.  Local subclass overrides this
        to prefer the ``-o`` report file.
        """
        json_path = files.get("stdout")
        if json_path is not None and json_path.exists():
            return parse_noir_json(json_path)
        return parse_noir_json_string(output)

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        """Return one ExecutionPass that scans the repo source tree."""
        assert context.repo is not None
        repo_path = context.registry.get_repo_path(self.name, context.repo)
        output_dir = ProjectPaths.from_canonical(
            context.base_path, context.project_name
        ).tool_output_dir("noir")
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        output_file = str(output_dir / f"{context.repo.name}_{ts}_oas3.json")

        techs = _compute_noir_techs(context.repo.languages or [])

        kwargs: dict[str, object] = {
            "source_path": repo_path,
            "output_file": output_file,
            "techs": techs,
        }

        pass_env: dict[str, str] | None = None
        global_config = context.config_manager.global_config
        noir_provider = global_config.noir_provider
        if noir_provider:
            provider_config = getattr(global_config, noir_provider, None)
            if provider_config is not None:
                # Noir's Ollama adapter is only activated by the "ollama"
                # keyword, not a raw URL. Pass the actual host via OLLAMA_HOST
                # so the adapter can reach a non-localhost server.
                kwargs["ai_provider_url"] = "ollama"
                kwargs["ai_model"] = provider_config.model
                if provider_config.num_ctx is not None:
                    kwargs["ai_max_token"] = provider_config.num_ctx
                pass_env = {"OLLAMA_HOST": provider_config.base_url}

        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs=kwargs,
                env=pass_env,
            )
        ]

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return pass_results[0]

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        return len(parsed_data.get("endpoints", []))
