"""Entry point for report draft generation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.reporting.blurbs import load_blurb
from application.reporting.draft_query import DraftQueryService
from application.reporting.drafts import SECTION_REGISTRY
from application.reporting.risk_level import compute_risk_level
from core.config.manager import ConfigManager
from core.llm.factory import get_llm_provider
from infrastructure.store import make_store

if TYPE_CHECKING:
    from rich.console import Console

logger = logging.getLogger(__name__)


def get_all_sections() -> list[str]:
    """Return the ordered list of all valid section names."""
    return list(SECTION_REGISTRY.keys())


def generate_draft(
    section: str,
    project: str,
    base_path: str | Path,
    console: Console,
    force: bool = False,
) -> None:
    """Generate a draft file for the named section.

    Args:
        section:   One of the registered section names.
        project:   Active project name.
        base_path: Application root path.
        console:   Rich Console for user output.
        force:     Skip overwrite confirmation if True.
    """
    if section not in SECTION_REGISTRY:
        valid = ", ".join(get_all_sections())
        console.print(
            f"[red]Unknown section:[/red] {section!r}\nValid sections: {valid}"
        )
        return

    draft_dir = Path(base_path) / "projects" / project / "reports" / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)

    llm = get_llm_provider("report", base_path)
    if not llm.is_available():
        console.print(
            "[red]LLM provider unavailable.[/red] "
            "Check config/global.json and ensure the provider is running."
        )
        return

    generator_cls = SECTION_REGISTRY[section]
    generator = generator_cls(llm, draft_dir)
    draft_path = generator.draft_path

    if draft_path.exists() and not force:
        console.print(
            f"Draft already exists: [bold]{draft_path}[/bold]\nOverwrite? [y/N] ",
            end="",
        )
        answer = input().strip().lower()
        if answer != "y":
            console.print("[dim]Aborted.[/dim]")
            return

    _, finding_repo, _, _ = make_store(base_path, project)
    query = DraftQueryService(finding_repo)
    findings = query.get_filtered_findings()

    if not findings:
        console.print(
            "[yellow]No triaged findings with should_report=1 found.[/yellow]"
            " Run triage before generating drafts."
        )
        return

    sev_dist = query.severity_distribution(findings)
    conf_dist = query.confidence_distribution(findings)
    risk_counts = query.build_risk_counts(findings)
    risk_level = compute_risk_level(risk_counts)

    config = ConfigManager(str(base_path))
    project_cfg = config.load_project_config(project)
    project_name = project_cfg.project_name if project_cfg else project
    engagement_date = project_cfg.created[:10] if project_cfg else ""
    repos = [r.name for r in project_cfg.repositories] if project_cfg else []

    context = _build_context(
        section=section,
        query=query,
        findings=findings,
        sev_dist=sev_dist,
        conf_dist=conf_dist,
        risk_counts=risk_counts,
        risk_level=risk_level,
        project_name=project_name,
        engagement_date=engagement_date,
        repos=repos,
        draft_dir=draft_dir,
    )

    with console.status(f"Generating {section}..."):
        content = generator.generate(context)

    draft_path.write_text(content, encoding="utf-8")
    console.print(f"[green]✓ Draft saved:[/green] {draft_path}")


def _build_context(
    section: str,
    query: DraftQueryService,
    findings: list[dict[str, Any]],
    sev_dist: dict[str, int],
    conf_dist: dict[str, int],
    risk_counts: Any,
    risk_level: Any,
    project_name: str,
    engagement_date: str,
    repos: list[str],
    draft_dir: Path,
) -> dict[str, Any]:
    """Assemble the context dict for the given section."""
    base: dict[str, Any] = {
        "project_name": project_name,
        "engagement_date": engagement_date,
        "repos": repos,
        "total": len(findings),
        "sev_dist": sev_dist,
        "conf_dist": conf_dist,
        "risk_counts": risk_counts,
        "risk_level": risk_level,
        "max_enumerate": 20,
    }

    if section in ("executive-summary", "risk-level"):
        return base

    if section == "critical-issues":
        base["top_findings"] = query.top_findings(findings, n=5)
        return base

    if section == "improvement-points":
        base["risk_type_groups"] = query.risk_type_groups(findings, top_n=8)
        return base

    if section == "scope-and-methodology":
        distinct_tools = query.distinct_tools(findings)
        base.update(
            {
                "tools": distinct_tools,
                "url_hosts": query.distinct_url_hosts(findings),
                "hosts": query.distinct_hosts(findings),
                "ecosystems": query.distinct_ecosystems(findings),
                "tools_blurb": _load_tools_blurb(distinct_tools),
            }
        )
        return base

    if section == "general-recommendations":
        base.update(
            {
                "risk_type_groups": query.risk_type_groups(findings, top_n=8),
                "recurring_by_risk_type": query.recurring_by_risk_type(findings),
                "improvement_points_draft": _load_existing_draft(
                    draft_dir, "improvement-points"
                ),
            }
        )
        return base

    return base


def _load_tools_blurb(tools: list[str]) -> str:
    """Load the tools-used blurb with the tool list substituted."""
    tool_list = "\n".join(f"- {t}" for t in tools) if tools else "(no tools recorded)"
    try:
        return load_blurb("tools-used", {"tool_list": tool_list})
    except Exception as exc:
        logger.warning("Could not load tools-used blurb: %s", exc)
        return tool_list


def _load_existing_draft(draft_dir: Path, section: str) -> str | None:
    """Return the content of an existing draft file, or None."""
    path = draft_dir / f"{section}.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read existing draft %r: %s", section, exc)
    return None
