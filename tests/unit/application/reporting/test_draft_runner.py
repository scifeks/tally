"""Unit tests for application.reporting.draft_runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from application.reporting.draft_runner import (
    _build_context,
    _build_rag_query,
    generate_draft,
)
from application.reporting.risk_level import RiskCounts, RiskLevel

_ZERO_RISK_COUNTS = RiskCounts(
    confirmed_critical=0,
    confirmed_high=0,
    prob_confirmed_medium=0,
    low_total=0,
    recurring=0,
)


def _make_console() -> MagicMock:
    console = MagicMock()
    console.status.return_value.__enter__ = MagicMock(return_value=None)
    console.status.return_value.__exit__ = MagicMock(return_value=False)
    return console


def _seed_draft(base: Path, project: str, section: str, text: str = "old") -> Path:
    draft_dir = base / "projects" / project / "reports" / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    path = draft_dir / f"{section}.md"
    path.write_text(text, encoding="utf-8")
    return path


class TestGenerateDraftPrompt:
    def test_force_skips_overwrite_prompt(self, tmp_path: Path) -> None:
        """force=True regenerates the draft without asking."""
        project = "acme"
        section = "executive-summary"
        existing = _seed_draft(tmp_path, project, section)

        with (
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
            patch("application.reporting.draft_runner.RAGEngine"),
            patch("application.reporting.draft_runner.QueryEngine") as mock_qe,
            patch("builtins.input") as mock_input,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_generator = MagicMock()
            mock_generator.draft_path = existing
            mock_generator.generate.return_value = "new content"
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_store.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )
            mock_qs.return_value.get_filtered_findings.return_value = [{"id": 1}]
            mock_qs.return_value.severity_distribution.return_value = {}
            mock_qs.return_value.confidence_distribution.return_value = {}
            mock_qs.return_value.build_risk_counts.return_value = _ZERO_RISK_COUNTS
            mock_cfg.return_value.load_project_config.return_value = None
            mock_qe.return_value.search.return_value = []

            generate_draft(
                section=section,
                project=project,
                base_path=tmp_path,
                console=_make_console(),
                force=True,
            )

        mock_input.assert_not_called()
        assert existing.read_text(encoding="utf-8") == "new content"

    def test_no_force_user_confirms_overwrites(self, tmp_path: Path) -> None:
        """force=False with 'y' answer proceeds and overwrites."""
        project = "acme"
        section = "risk-level"
        existing = _seed_draft(tmp_path, project, section)

        with (
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
            patch("application.reporting.draft_runner.RAGEngine"),
            patch("application.reporting.draft_runner.QueryEngine") as mock_qe,
            patch("builtins.input", return_value="y"),
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_generator = MagicMock()
            mock_generator.draft_path = existing
            mock_generator.generate.return_value = "updated"
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_store.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )
            mock_qs.return_value.get_filtered_findings.return_value = [{"id": 1}]
            mock_qs.return_value.severity_distribution.return_value = {}
            mock_qs.return_value.confidence_distribution.return_value = {}
            mock_qs.return_value.build_risk_counts.return_value = _ZERO_RISK_COUNTS
            mock_cfg.return_value.load_project_config.return_value = None
            mock_qe.return_value.search.return_value = []

            generate_draft(
                section=section,
                project=project,
                base_path=tmp_path,
                console=_make_console(),
                force=False,
            )

        assert existing.read_text(encoding="utf-8") == "updated"

    def test_no_force_user_declines_aborts(self, tmp_path: Path) -> None:
        """force=False with 'n' answer does not overwrite the draft."""
        project = "acme"
        section = "risk-level"
        existing = _seed_draft(tmp_path, project, section, text="original")

        with (
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("builtins.input", return_value="n"),
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_generator = MagicMock()
            mock_generator.draft_path = existing
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)

            console = _make_console()
            generate_draft(
                section=section,
                project=project,
                base_path=tmp_path,
                console=console,
                force=False,
            )

        assert existing.read_text(encoding="utf-8") == "original"
        printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "Aborted" in printed

    def test_invalid_section_prints_error(self, tmp_path: Path) -> None:
        """Unknown section name prints an error and returns."""
        console = _make_console()
        generate_draft(
            section="nonexistent-section",
            project="acme",
            base_path=tmp_path,
            console=console,
            force=False,
        )
        printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "Unknown section" in printed

    def test_skip_triage_passes_flag_to_query_service(self, tmp_path: Path) -> None:
        """skip_triage=True calls get_filtered_findings(skip_triage=True)."""
        project = "acme"
        section = "executive-summary"

        with (
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
            patch("application.reporting.draft_runner.RAGEngine"),
            patch("application.reporting.draft_runner.QueryEngine") as mock_qe,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_generator = MagicMock()
            draft_path = (
                tmp_path / "projects" / project / "reports" / "draft" / f"{section}.md"
            )
            mock_generator.draft_path = draft_path
            mock_generator.generate.return_value = "content"
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_store.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )
            mock_qs.return_value.get_filtered_findings.return_value = [{"id": 1}]
            mock_qs.return_value.severity_distribution.return_value = {}
            mock_qs.return_value.confidence_distribution.return_value = {}
            mock_qs.return_value.build_risk_counts.return_value = _ZERO_RISK_COUNTS
            mock_cfg.return_value.load_project_config.return_value = None
            mock_qe.return_value.search.return_value = []

            generate_draft(
                section=section,
                project=project,
                base_path=tmp_path,
                console=_make_console(),
                force=True,
                skip_triage=True,
            )

        mock_qs.return_value.get_filtered_findings.assert_called_once_with(
            skip_triage=True
        )

    def test_skip_triage_empty_findings_shows_scan_message(
        self, tmp_path: Path
    ) -> None:
        """When skip_triage=True and no findings, message says 'Run a scan first'."""
        project = "acme"
        section = "executive-summary"

        with (
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_generator = MagicMock()
            draft_path = (
                tmp_path / "projects" / project / "reports" / "draft" / f"{section}.md"
            )
            mock_generator.draft_path = draft_path
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_store.return_value = (
                MagicMock(),
                MagicMock(),
                MagicMock(),
                MagicMock(),
            )
            mock_qs.return_value.get_filtered_findings.return_value = []
            mock_cfg.return_value.load_project_config.return_value = None

            console = _make_console()
            generate_draft(
                section=section,
                project=project,
                base_path=tmp_path,
                console=console,
                force=True,
                skip_triage=True,
            )

        printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "scan" in printed.lower()
        assert "triage" not in printed.lower()


# ---------------------------------------------------------------------------
# _build_rag_query
# ---------------------------------------------------------------------------


class TestBuildRagQuery:
    def test_scope_and_methodology_returns_none(self) -> None:
        assert _build_rag_query("scope-and-methodology", {}) is None

    def test_executive_summary_mentions_severity(self) -> None:
        result = _build_rag_query("executive-summary", {})
        assert result is not None
        assert "critical" in result
        assert "high" in result

    def test_risk_level_mentions_severity_and_tool(self) -> None:
        result = _build_rag_query("risk-level", {})
        assert result is not None
        assert "severity" in result
        assert "tool" in result

    def test_critical_issues_no_terms_returns_base(self) -> None:
        result = _build_rag_query("critical-issues", {"top_findings": []})
        assert result is not None
        assert "critical" in result
        assert "high" in result

    def test_critical_issues_includes_vulnerability_id_from_findings(self) -> None:
        ctx = {
            "top_findings": [
                {"vulnerability_id": "CVE-2023-001", "cwe": None, "risk_type": None}
            ]
        }
        result = _build_rag_query("critical-issues", ctx)
        assert result is not None
        assert "CVE-2023-001" in result

    def test_improvement_points_no_groups_returns_base(self) -> None:
        result = _build_rag_query("improvement-points", {"risk_type_groups": []})
        assert result is not None
        assert "recurring" in result

    def test_improvement_points_includes_group_names(self) -> None:
        ctx = {"risk_type_groups": [("injection", 5), ("secrets", 2)]}
        result = _build_rag_query("improvement-points", ctx)
        assert result is not None
        assert "injection" in result

    def test_general_recommendations_no_groups_returns_base(self) -> None:
        result = _build_rag_query("general-recommendations", {"risk_type_groups": []})
        assert result is not None
        assert "remediation" in result

    def test_general_recommendations_includes_group_names(self) -> None:
        ctx = {"risk_type_groups": [("injection", 4), ("secrets", 2)]}
        result = _build_rag_query("general-recommendations", ctx)
        assert result is not None
        assert "injection" in result

    def test_unknown_section_returns_none(self) -> None:
        assert _build_rag_query("nonexistent-section", {}) is None


# ---------------------------------------------------------------------------
# _build_context
# ---------------------------------------------------------------------------

_BASE_RISK_COUNTS = RiskCounts(
    confirmed_critical=0,
    confirmed_high=1,
    prob_confirmed_medium=2,
    low_total=0,
    recurring=0,
)
_BASE_RISK_LEVEL = RiskLevel.HIGH


def _make_query(
    top_findings: list | None = None,
    risk_type_groups: list | None = None,
    recurring: dict | None = None,
    tools: list | None = None,
    url_hosts: list | None = None,
    ecosystems: list | None = None,
) -> MagicMock:
    q = MagicMock()
    q.top_findings.return_value = top_findings or []
    q.risk_type_groups.return_value = risk_type_groups or []
    q.recurring_by_risk_type.return_value = recurring or {}
    q.distinct_tools.return_value = tools or []
    q.distinct_url_hosts.return_value = url_hosts or []
    q.distinct_ecosystems.return_value = ecosystems or []
    return q


def _call_build_context(
    section: str,
    query: MagicMock,
    tmp_path: Path,
    findings: list | None = None,
) -> dict:
    return _build_context(
        section=section,
        query=query,
        findings=findings or [{"id": 1}],
        sev_dist={"high": 1},
        conf_dist={"confirmed": 1},
        risk_counts=_BASE_RISK_COUNTS,
        risk_level=_BASE_RISK_LEVEL,
        project_name="TestCo",
        engagement_date="2025-01-01",
        repos=["repo/a"],
        draft_dir=tmp_path,
        prefix="TC",
    )


class TestBuildContext:
    def test_executive_summary_has_base_keys(self, tmp_path: Path) -> None:
        ctx = _call_build_context("executive-summary", _make_query(), tmp_path)
        assert ctx["project_name"] == "TestCo"
        assert ctx["engagement_date"] == "2025-01-01"
        assert ctx["repos"] == ["repo/a"]
        assert ctx["total"] == 1
        assert ctx["risk_level"] is _BASE_RISK_LEVEL
        assert "top_findings" not in ctx

    def test_risk_level_has_base_keys_only(self, tmp_path: Path) -> None:
        ctx = _call_build_context("risk-level", _make_query(), tmp_path)
        assert ctx["project_name"] == "TestCo"
        assert "top_findings" not in ctx
        assert "risk_type_groups" not in ctx

    def test_critical_issues_includes_top_findings(self, tmp_path: Path) -> None:
        findings = [{"id": 1, "severity": "high"}]
        query = _make_query(top_findings=findings)
        ctx = _call_build_context("critical-issues", query, tmp_path)
        assert ctx["top_findings"] == findings

    def test_improvement_points_includes_risk_type_groups(self, tmp_path: Path) -> None:
        groups = [("injection", 3)]
        query = _make_query(risk_type_groups=groups)
        ctx = _call_build_context("improvement-points", query, tmp_path)
        assert ctx["risk_type_groups"] == groups

    def test_scope_includes_tools_and_hosts(self, tmp_path: Path) -> None:
        query = _make_query(
            tools=["semgrep"],
            url_hosts=["example.com"],
            ecosystems=["PyPI"],
        )
        with patch(
            "application.reporting.draft_runner._load_tools_blurb",
            return_value="blurb text",
        ):
            ctx = _call_build_context("scope-and-methodology", query, tmp_path)
        assert ctx["tools"] == ["semgrep"]
        assert ctx["url_hosts"] == ["example.com"]
        assert ctx["ecosystems"] == ["PyPI"]
        assert ctx["tools_blurb"] == "blurb text"

    def test_general_recommendations_includes_recurring(self, tmp_path: Path) -> None:
        recurring = {"injection": [{"id": 1}]}
        query = _make_query(
            risk_type_groups=[("injection", 2)],
            recurring=recurring,
        )
        ctx = _call_build_context("general-recommendations", query, tmp_path)
        assert ctx["recurring_by_risk_type"] == recurring
        assert ctx["risk_type_groups"] == [("injection", 2)]

    def test_general_recommendations_loads_existing_improvement_draft(
        self, tmp_path: Path
    ) -> None:
        draft_dir = tmp_path / "draft"
        draft_dir.mkdir()
        (draft_dir / "improvement-points.md").write_text(
            "existing draft", encoding="utf-8"
        )
        ctx = _build_context(
            section="general-recommendations",
            query=_make_query(),
            findings=[{"id": 1}],
            sev_dist={},
            conf_dist={},
            risk_counts=_BASE_RISK_COUNTS,
            risk_level=_BASE_RISK_LEVEL,
            project_name="TestCo",
            engagement_date="2025-01-01",
            repos=[],
            draft_dir=draft_dir,
        )
        assert ctx["improvement_points_draft"] == "existing draft"

    def test_general_recommendations_improvement_draft_none_when_missing(
        self, tmp_path: Path
    ) -> None:
        ctx = _call_build_context("general-recommendations", _make_query(), tmp_path)
        assert ctx["improvement_points_draft"] is None
