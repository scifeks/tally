"""Phase 6 integration tests: generate_draft() injects rag_context from ChromaDB."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import chromadb.utils.embedding_functions as ef
import pytest

from application.project import ProjectManager
from application.rag.engine import RAGEngine
from application.rag.query import QueryEngine
from application.reporting.draft_runner import generate_draft
from application.reporting.risk_level import RiskCounts

pytestmark = pytest.mark.integration

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


def _make_rag_engine(base_path: str, project_name: str) -> RAGEngine:
    default_fn = ef.DefaultEmbeddingFunction()
    with patch.object(RAGEngine, "_build_embedding_function", return_value=default_fn):
        return RAGEngine(project_name=project_name, base_path=base_path)


def _make_console() -> MagicMock:
    console = MagicMock()
    console.status.return_value.__enter__ = MagicMock(return_value=None)
    console.status.return_value.__exit__ = MagicMock(return_value=False)
    return console


@pytest.fixture()
def phase6_env(tmp_path: Path) -> dict:
    _write_global_config(tmp_path)
    project_name = "test-phase6"
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(project_name)
    pm.save_project(project_name, [])

    engine = _make_rag_engine(str(tmp_path), project_name)
    try:
        engine.add_documents(
            texts=[
                "[semgrep] Rule: python.flask.sqli | Severity: high"
                " | Description: SQL injection via user input | CWE: CWE-89"
            ],
            metadatas=[{"tool": "semgrep", "profile": "default"}],
            ids=["doc-1"],
        )
    finally:
        engine.close()

    return {"base_path": str(tmp_path), "project_name": project_name}


class TestPhase6RagDraft:
    def test_rag_context_populated_when_chroma_has_docs(
        self, phase6_env: dict, tmp_path: Path
    ) -> None:
        """generate_draft() passes non-empty rag_context when ChromaDB has docs."""
        base_path = phase6_env["base_path"]
        project = phase6_env["project_name"]
        section = "executive-summary"

        captured_context: dict = {}

        def _capture_generate(ctx: dict) -> str:
            captured_context.update(ctx)
            return "draft content"

        mock_generator = MagicMock()
        mock_generator.draft_path = (
            Path(base_path)
            / "projects"
            / project
            / "reports"
            / "draft"
            / f"{section}.md"
        )
        mock_generator.generate.side_effect = _capture_generate

        default_fn = ef.DefaultEmbeddingFunction()
        with (
            patch(
                "application.reporting.draft_runner.RAGEngine",
                side_effect=lambda **kw: _make_rag_engine(
                    kw["base_path"], kw["project_name"]
                ),
            ),
            patch(
                "application.reporting.draft_runner.QueryEngine",
                side_effect=lambda engine: QueryEngine(engine),
            ),
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
            patch.object(
                RAGEngine, "_build_embedding_function", return_value=default_fn
            ),
        ):
            mock_llm.return_value.is_available.return_value = True
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

            generate_draft(
                section=section,
                project=project,
                base_path=base_path,
                console=_make_console(),
                force=True,
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
        mock_generator.draft_path = (
            Path(base_path)
            / "projects"
            / project
            / "reports"
            / "draft"
            / f"{section}.md"
        )
        mock_generator.generate.side_effect = _capture_generate

        with (
            patch("application.reporting.draft_runner.RAGEngine"),
            patch("application.reporting.draft_runner.QueryEngine") as mock_qe,
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_qe.return_value.search.return_value = []
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

            generate_draft(
                section=section,
                project=project,
                base_path=base_path,
                console=_make_console(),
                force=True,
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
        mock_generator.draft_path = draft_path
        mock_generator.generate.return_value = "draft despite error"

        with (
            patch("application.reporting.draft_runner.RAGEngine"),
            patch("application.reporting.draft_runner.QueryEngine") as mock_qe,
            patch("application.reporting.draft_runner.get_llm_provider") as mock_llm,
            patch("application.reporting.draft_runner.make_store") as mock_store,
            patch("application.reporting.draft_runner.DraftQueryService") as mock_qs,
            patch("application.reporting.draft_runner.SECTION_REGISTRY") as mock_reg,
            patch("application.reporting.draft_runner.ConfigManager") as mock_cfg,
        ):
            mock_llm.return_value.is_available.return_value = True
            mock_qe.return_value.search.side_effect = RuntimeError("chroma down")
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

            generate_draft(
                section=section,
                project=project,
                base_path=base_path,
                console=_make_console(),
                force=True,
            )

        assert draft_path.exists()
        assert draft_path.read_text(encoding="utf-8") == "draft despite error"
