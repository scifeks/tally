"""Docker psalm wrapper.

Generated files live in the repo mount because host /tmp
is invisible to the container.
"""

import shutil
import tempfile
from pathlib import Path

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext, ExecutionPass
from infrastructure.tools.wrappers.base.psalm import BasePsalmTool
from infrastructure.tools.wrappers.docker._docker_exec import (
    build_docker_exec,
)


class PsalmDockerTool(BasePsalmTool):
    def __init__(self, config) -> None:
        self._container_name: str = config.container.name
        self._tool_path: str = config.container.tool_path
        self._docker_path: str = ""

    @property
    def command(self) -> str:
        return "docker"

    def check_available(self) -> bool:
        return True

    def get_version(self) -> str | None:
        return None

    def build_execution_passes(
        self,
        context: ExecutionContext,
    ) -> list[ExecutionPass]:
        assert context.repo is not None
        assert context.service is not None

        self._docker_path = context.service.docker_path
        if not self._docker_path:
            raise ValueError(
                "docker_path is not configured for this "
                "repository. Use 'repo edit' to set the "
                "container mount path."
            )

        host_repo_path = context.repo.path
        self._temp_dir = tempfile.mkdtemp(prefix=".tally-psalm-", dir=host_repo_path)
        temp_name = Path(self._temp_dir).name

        config_path = self._generate_docker_config(
            self._temp_dir,
            context.repo,
        )
        self._sarif_path = Path(self._temp_dir) / "results.sarif"

        container_temp = f"{self._docker_path}/{temp_name}"
        container_config = f"{container_temp}/{config_path.name}"
        container_sarif = f"{container_temp}/results.sarif"

        return [
            ExecutionPass(
                label_suffix=context.repo.name,
                kwargs={
                    "repo_path": self._docker_path,
                    "config_path": container_config,
                    "sarif_path": container_sarif,
                },
            ),
        ]

    def _generate_docker_config(
        self,
        host_temp_dir: str,
        repo: Repository,
    ) -> Path:
        """Generate psalm.xml with container-relative paths."""
        source_dirs = self._find_source_dirs(repo.path)
        host_stubs = self._resolve_stubs(repo.psalm_stubs)

        stubs_subdir = Path(host_temp_dir) / "stubs"
        stubs_subdir.mkdir(exist_ok=True)
        relative_stub_paths = []
        for host_stub in host_stubs:
            stub_name = Path(host_stub).name
            shutil.copy2(host_stub, stubs_subdir / stub_name)
            relative_stub_paths.append(f"stubs/{stub_name}")

        # Psalm resolves paths relative to the config file.
        # The config sits one level below the repo root.
        relative_src_dirs = [f"../{d}" for d in source_dirs]
        autoloader = (
            "../vendor/autoload.php"
            if (Path(repo.path) / "vendor" / "autoload.php").exists()
            else None
        )

        xml_str = self._build_docker_xml(
            relative_src_dirs, relative_stub_paths, autoloader
        )
        config_path = Path(host_temp_dir) / "psalm.xml"
        config_path.write_text(xml_str)
        return config_path

    def _build_docker_xml(
        self,
        source_dirs: list[str],
        stub_paths: list[str],
        autoloader: str | None,
    ) -> str:
        lines = [
            '<?xml version="1.0"?>',
            "<psalm",
            '    errorLevel="1"',
            '    runTaintAnalysis="true"',
            '    xmlns="https://getpsalm.org/schema/config"',
        ]
        if autoloader:
            lines.append(f'    autoloader="{autoloader}"')
        lines.append(">")
        lines.append("    <projectFiles>")

        for dir_name in source_dirs:
            lines.append(f'        <directory name="{dir_name}" />')

        lines.append("    </projectFiles>")

        if stub_paths:
            lines.append("    <stubs>")
            for stub_path in stub_paths:
                lines.append(f'        <file name="{stub_path}" />')
            lines.append("    </stubs>")

        lines.append("</psalm>")
        return "\n".join(lines)

    def build_command(self, **kwargs) -> list[str]:
        repo_path: str = kwargs.get("repo_path", "")
        config_path: str = kwargs.get("config_path", "")
        sarif_path: str = kwargs.get("sarif_path", "")

        if not repo_path:
            raise ValueError(
                "docker_path is not configured for this "
                "repository. Use 'repo edit' to set the "
                "container mount path."
            )

        tool_args = [
            f"--config={config_path}",
            f"--report={sarif_path}",
            "--no-cache",
            "--no-progress",
        ]

        return build_docker_exec(
            self._container_name,
            self._tool_path,
            tool_args,
        )
