"""MCP triage orchestrator — entry points delegating to TriageRunner."""

import dataclasses
from pathlib import Path

from .triage import TriageRunner

_APP_ROOT = Path(__file__).parent.parent


def run_triage(project: str) -> dict[str, int]:
    """Run AI triage sessions for untriaged findings."""
    runner = TriageRunner.for_project(project)
    return dataclasses.asdict(runner.run())


def run_triage_batch_only(project: str) -> int:
    """Run only the batching phase — no MCP server, no Claude sessions."""
    runner = TriageRunner.for_project(project)
    _run_id, total = runner.batch()
    return total


def run_triage_dry_run(project: str) -> int:
    """Batch phase + render prompts to DEBUG log. No MCP server, no Claude."""
    runner = TriageRunner.for_project(project)
    return runner.run_dry_run()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    print(run_triage(args.project))
