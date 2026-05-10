"""Integration tests: run_draft() injects rag_context from ChromaDB."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.project import ProjectManager
from application.reporting.draft_orchestrator import DraftRequest, run_draft
from application.reporting.risk_level import RiskCounts
from domain.findings.entry import Finding


def _seed_finding() -> Finding:
    return Finding(
        id=1,
        fingerprint=None,
        run_id=None,
        tool=None,
        domain=None,
        segment=None,
    )


pytestmark = pytest.mark.integration


class _AlwaysConfirm:
    def confirm(self, question: str, *, default: bool = False) -> bool:
        return True

    def approve_all_remaining(self) -> None:
        pass


_TALLY_ROOT = Path(__file__).resolve().parents[3]

_ZERO_RISK_COUNTS = RiskCounts(
    confirmed_critical=0,
    confirmed_high=0,
    prob_confirmed_medium=0,
    low_total=0,
    recurring=0,
)


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _make_mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.get.return_value = None
    return repo


@pytest.fixture()
def phase6_env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    project_name = "test-phase6"
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(project_name)
    pm.save_project(project_name)

    return {"base_path": str(tmp_path), "project_name": project_name}


class TestPhase6RagDraft:
    def test_rag_context_populated_when_chroma_has_docs(self, phase6_env: dict) -> None:
        """run_draft() passes non-empty rag_context when ChromaDB has docs."""
        base_path = phase6_env["base_path"]
        project = phase6_env["project_name"]
        section = "executive-summary"

        captured_context: dict = {}

        def _capture_generate(ctx: dict) -> str:
            captured_context.update(ctx)
            return "draft content"

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = _capture_generate

        with (
            patch(
                "application.reporting.draft_orchestrator.make_chromadb_vector_index"
            ),
            patch("application.reporting.draft_orchestrator.get_embedding_provider"),
            patch("application.reporting.draft_orchestrator.FindingKnowledgeBase"),
            patch("application.reporting.draft_orchestrator.QueryEngine") as mock_qe,
            patch(
                "application.reporting.draft_orchestrator.get_llm_provider"
            ) as mock_llm,
            patch(
                "application.reporting.draft_orchestrator.DraftQueryService"
            ) as mock_qs,
            patch(
                "application.reporting.draft_orchestrator.SECTION_REGISTRY"
            ) as mock_reg,
            patch("application.reporting.draft_orchestrator.ConfigManager") as mock_cfg,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_qe.return_value.search.return_value = [
                {
                    "id": "doc-1",
                    "document": (
                        "[semgrep] Rule: python.flask.sqli | "
                        "Severity: high | CWE: CWE-89"
                    ),
                    "metadata": {"tool": "semgrep", "profile": "default"},
                    "distance": 0.1,
                }
            ]
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_qs.return_value.get_filtered_findings.return_value = [_seed_finding()]
            mock_qs.return_value.severity_distribution.return_value = {}
            mock_qs.return_value.confidence_distribution.return_value = {}
            mock_qs.return_value.build_risk_counts.return_value = _ZERO_RISK_COUNTS
            mock_cfg.return_value.load_project_config.return_value = None

            request = DraftRequest(
                project=project,
                base_path=Path(base_path),
                section=section,
                force_overwrite=True,
            )
            run_draft(
                request,
                prompt=_AlwaysConfirm(),
                repo=_make_mock_repo(),
                finding_repo=_make_mock_repo(),
                repo_repo=_make_mock_repo(),
                event_sink=None,
            )

        assert "rag_context" in captured_context
        assert captured_context["rag_context"] != ""

    def test_rag_context_absent_for_scope_section(self, phase6_env: dict) -> None:
        """scope-and-methodology never receives rag_context."""
        base_path = phase6_env["base_path"]
        project = phase6_env["project_name"]
        section = "scope-and-methodology"

        captured_context: dict = {}

        def _capture_generate(ctx: dict) -> str:
            captured_context.update(ctx)
            return "draft content"

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = _capture_generate

        with (
            patch(
                "application.reporting.draft_orchestrator.make_chromadb_vector_index"
            ),
            patch("application.reporting.draft_orchestrator.get_embedding_provider"),
            patch("application.reporting.draft_orchestrator.FindingKnowledgeBase"),
            patch("application.reporting.draft_orchestrator.QueryEngine") as mock_qe,
            patch(
                "application.reporting.draft_orchestrator.get_llm_provider"
            ) as mock_llm,
            patch(
                "application.reporting.draft_orchestrator.DraftQueryService"
            ) as mock_qs,
            patch(
                "application.reporting.draft_orchestrator.SECTION_REGISTRY"
            ) as mock_reg,
            patch("application.reporting.draft_orchestrator.ConfigManager") as mock_cfg,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_qe.return_value.search.return_value = []
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_qs.return_value.get_filtered_findings.return_value = [_seed_finding()]
            mock_qs.return_value.severity_distribution.return_value = {}
            mock_qs.return_value.confidence_distribution.return_value = {}
            mock_qs.return_value.build_risk_counts.return_value = _ZERO_RISK_COUNTS
            mock_cfg.return_value.load_project_config.return_value = None

            request = DraftRequest(
                project=project,
                base_path=Path(base_path),
                section=section,
                force_overwrite=True,
            )
            run_draft(
                request,
                prompt=_AlwaysConfirm(),
                repo=_make_mock_repo(),
                finding_repo=_make_mock_repo(),
                repo_repo=_make_mock_repo(),
                event_sink=None,
            )

        assert captured_context.get("rag_context", "") == ""
        mock_qe.return_value.search.assert_not_called()

    def test_chroma_failure_does_not_abort_draft(self, phase6_env: dict) -> None:
        """A ChromaDB exception is caught and the draft is still written."""
        base_path = phase6_env["base_path"]
        project = phase6_env["project_name"]
        section = "executive-summary"

        draft_path = (
            Path(base_path)
            / "projects"
            / project
            / "reports"
            / "draft"
            / f"{section}.md"
        )

        mock_generator = MagicMock()
        mock_generator.generate.return_value = "draft despite error"

        with (
            patch(
                "application.reporting.draft_orchestrator.make_chromadb_vector_index"
            ),
            patch("application.reporting.draft_orchestrator.get_embedding_provider"),
            patch("application.reporting.draft_orchestrator.FindingKnowledgeBase"),
            patch("application.reporting.draft_orchestrator.QueryEngine") as mock_qe,
            patch(
                "application.reporting.draft_orchestrator.get_llm_provider"
            ) as mock_llm,
            patch(
                "application.reporting.draft_orchestrator.DraftQueryService"
            ) as mock_qs,
            patch(
                "application.reporting.draft_orchestrator.SECTION_REGISTRY"
            ) as mock_reg,
            patch("application.reporting.draft_orchestrator.ConfigManager") as mock_cfg,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_qe.return_value.search.side_effect = RuntimeError("chroma down")
            mock_reg.__contains__ = MagicMock(return_value=True)
            mock_reg.__getitem__ = MagicMock(return_value=lambda *_: mock_generator)
            mock_qs.return_value.get_filtered_findings.return_value = [_seed_finding()]
            mock_qs.return_value.severity_distribution.return_value = {}
            mock_qs.return_value.confidence_distribution.return_value = {}
            mock_qs.return_value.build_risk_counts.return_value = _ZERO_RISK_COUNTS
            mock_cfg.return_value.load_project_config.return_value = None

            request = DraftRequest(
                project=project,
                base_path=Path(base_path),
                section=section,
                force_overwrite=True,
            )
            run_draft(
                request,
                prompt=_AlwaysConfirm(),
                repo=_make_mock_repo(),
                finding_repo=_make_mock_repo(),
                repo_repo=_make_mock_repo(),
                event_sink=None,
            )

        assert draft_path.exists()
        assert draft_path.read_text(encoding="utf-8") == "draft despite error"
