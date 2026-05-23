#!/usr/bin/env python3
"""Start the Tally web app for Playwright e2e tests.

Acquires the instance lock, bootstraps into an isolated base path,
generates a random handshake token (written to .auth/token.txt),
and runs the FastAPI + Vite servers on dedicated e2e ports.
"""

import argparse
import atexit
import fcntl
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

_LOCK_PATH = Path.home() / ".tally-instance.lock"
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[2]

sys.path.insert(0, str(_PROJECT_ROOT))


def acquire_instance_lock() -> None:
    fd = os.open(str(_LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        print(
            "Another Tally instance is already running. "
            "Stop it before starting e2e tests.",
            file=sys.stderr,
        )
        sys.exit(1)
    os.write(fd, f"{os.getpid()}\n".encode())
    os.ftruncate(fd, os.lseek(fd, 0, os.SEEK_CUR))
    atexit.register(os.close, fd)


def write_env_local(ui_dir: Path, host: str, api_port: int, vite_port: int) -> None:
    content = (
        f"TALLY_HOST={host}\n"
        f"TALLY_VITE_PORT={vite_port}\n"
        f"VITE_API_BASE_URL=http://{host}:{api_port}\n"
    )
    target = ui_dir / ".env.local"
    tmp = target.with_suffix(".env.local.tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def start_vite(ui_dir: Path) -> subprocess.Popen[bytes]:
    env = {**os.environ, "FORCE_COLOR": "0"}
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=ui_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    atexit.register(lambda: (proc.terminate(), proc.wait(timeout=5)))
    return proc


def main() -> None:
    parser = argparse.ArgumentParser(description="Start Tally for e2e tests")
    parser.add_argument("--api-port", type=int, default=8181, help="FastAPI port")
    parser.add_argument(
        "--vite-port", type=int, default=3100, help="Vite dev server port"
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    args = parser.parse_args()

    acquire_instance_lock()

    base_path = str(_SCRIPT_DIR / ".tally-data")
    Path(base_path).mkdir(exist_ok=True)
    (_SCRIPT_DIR / ".auth").mkdir(exist_ok=True)

    from application.bootstrap import BootstrapService
    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.project_registry import (
        ProjectRegistryRepository,
    )
    from infrastructure.store.repositories.runs import RunRepository
    from web.server import create_web_app

    registry_repo = ProjectRegistryRepository(Path(base_path) / "tally.db")
    project_registry = ProjectRegistryService(registry_repo)
    tool_registry = ToolRegistry()

    BootstrapService(
        registry_repo=registry_repo,
        project_registry=project_registry,
        tool_registry=tool_registry,
        base_path=base_path,
        run_repo_factory=lambda p: RunRepository(ConnectionFactory(p)),
    ).run()

    from application.project.manager import ProjectManager

    pm = ProjectManager(base_path=base_path, registry=project_registry)
    if not any(p.name == "e2e-test" for p in project_registry.list_active()):
        pm.create_project_dirs("e2e-test")
        pm.save_project(
            "e2e-test",
            company_name="E2E Corp",
            department_name="Security",
            abbreviation="E2E",
        )

    token = secrets.token_hex(16)
    token_path = _SCRIPT_DIR / ".auth" / "token.txt"
    token_path.write_text(token, encoding="utf-8")

    app = create_web_app(
        base_path,
        args.api_port,
        token,
        [f"http://{args.host}:{args.vite_port}"],
        project_registry=project_registry,
        tool_registry=tool_registry,
    )

    ui_dir = _PROJECT_ROOT / "ui"
    write_env_local(ui_dir, args.host, args.api_port, args.vite_port)
    start_vite(ui_dir)

    vite_url = f"http://{args.host}:{args.vite_port}"
    if not wait_for_port(args.host, args.vite_port, timeout=15.0):
        print(f"Vite did not start within 15s at {vite_url}", file=sys.stderr)
        sys.exit(1)

    print(f"Tally e2e server ready at {vite_url}")

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.api_port, log_level="warning")


if __name__ == "__main__":
    main()
