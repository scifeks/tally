"""Unit tests for application.reporting.draft_runner.generate_draft()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from application.reporting.draft_runner import generate_draft
from application.reporting.risk_level import RiskCounts

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
