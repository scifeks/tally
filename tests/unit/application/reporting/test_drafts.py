"""Unit tests for application.reporting.drafts SectionDraftGenerator subclasses."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.reporting.drafts import (
    SECTION_REGISTRY,
    CriticalIssuesGenerator,
    ExecutiveSummaryGenerator,
    GeneralRecommendationsGenerator,
    ImprovementPointsGenerator,
    RiskLevelSectionGenerator,
    ScopeMethodologyGenerator,
)
from application.reporting.risk_level import RiskCounts, RiskLevel
from domain.findings.entry import Finding


def _make_finding(**kwargs: Any) -> Finding:
    defaults: dict[str, Any] = {
        "id": 0,
        "fingerprint": None,
        "run_id": None,
        "tool": None,
        "domain": None,
        "segment": None,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


_ZERO_RISK_COUNTS = RiskCounts(
    confirmed_critical=0,
    confirmed_high=0,
    prob_confirmed_medium=0,
    low_total=0,
    recurring=0,
)
_HIGH_RISK_COUNTS = RiskCounts(
    confirmed_critical=0,
    confirmed_high=2,
    prob_confirmed_medium=3,
    low_total=1,
    recurring=1,
)


def _make_generator(cls: type, tmp_path: Path) -> Any:
    return cls(MagicMock(), tmp_path)


def _base_ctx() -> dict:
    return {
        "project_name": "Acme Corp",
        "engagement_date": "2025-06-01",
        "repos": ["acme/backend", "acme/frontend"],
        "total": 12,
        "sev_dist": {"critical": 1, "high": 2, "medium": 3},
        "conf_dist": {"confirmed": 4, "probable": 2},
        "risk_counts": _HIGH_RISK_COUNTS,
        "risk_level": RiskLevel.HIGH,
        "max_enumerate": 20,
        "finding_id_prefix": "ACM",
    }


# Registry


class TestSectionRegistry:
    def test_all_six_sections_registered(self) -> None:
        expected = {
            "executive-summary",
            "risk-level",
            "critical-issues",
            "improvement-points",
            "scope-and-methodology",
            "general-recommendations",
        }
        assert set(SECTION_REGISTRY.keys()) == expected

    def test_registry_maps_to_correct_classes(self) -> None:
        assert SECTION_REGISTRY["executive-summary"] is ExecutiveSummaryGenerator
        assert SECTION_REGISTRY["risk-level"] is RiskLevelSectionGenerator
        assert SECTION_REGISTRY["critical-issues"] is CriticalIssuesGenerator
        assert SECTION_REGISTRY["improvement-points"] is ImprovementPointsGenerator
        assert SECTION_REGISTRY["scope-and-methodology"] is ScopeMethodologyGenerator
        assert (
            SECTION_REGISTRY["general-recommendations"]
            is GeneralRecommendationsGenerator
        )


# draft_path property (parametrized)


@pytest.mark.parametrize(
    "cls, expected_section",
    [
        (ExecutiveSummaryGenerator, "executive-summary"),
        (RiskLevelSectionGenerator, "risk-level"),
        (CriticalIssuesGenerator, "critical-issues"),
        (ImprovementPointsGenerator, "improvement-points"),
        (ScopeMethodologyGenerator, "scope-and-methodology"),
        (GeneralRecommendationsGenerator, "general-recommendations"),
    ],
)
class TestDraftPath:
    def test_draft_path_uses_section_name(
        self,
        cls: type,
        expected_section: str,
        tmp_path: Path,
    ) -> None:
        gen = _make_generator(cls, tmp_path)
        assert gen.draft_path == tmp_path / f"{expected_section}.md"


# ExecutiveSummaryGenerator


class TestExecutiveSummaryGenerator:
    def _gen(self, tmp_path: Path) -> Any:
        return _make_generator(ExecutiveSummaryGenerator, tmp_path)

    def test_prompt_contains_project_name(self, tmp_path: Path) -> None:
        assert "Acme Corp" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_risk_level(self, tmp_path: Path) -> None:
        assert "High" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_repos(self, tmp_path: Path) -> None:
        assert "acme/backend" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_engagement_date(self, tmp_path: Path) -> None:
        assert "2025-06-01" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_total_findings(self, tmp_path: Path) -> None:
        assert "12" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_severity_distribution(self, tmp_path: Path) -> None:
        prompt = self._gen(tmp_path)._build_prompt(_base_ctx())
        assert "Critical: 1" in prompt
        assert "High: 2" in prompt

    def test_prompt_includes_rag_context_when_present(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["rag_context"] = "SQL injection in login form"
        assert "SQL injection in login form" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_omits_rag_block_when_absent(self, tmp_path: Path) -> None:
        assert "semantic search" not in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_includes_confirmed_critical_in_risk_basis(
        self, tmp_path: Path
    ) -> None:
        ctx = _base_ctx()
        ctx["risk_counts"] = RiskCounts(
            confirmed_critical=2,
            confirmed_high=0,
            prob_confirmed_medium=0,
            low_total=0,
            recurring=0,
        )
        assert "confirmed critical" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_empty_repos_shows_none_recorded(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["repos"] = []
        assert "(none recorded)" in self._gen(tmp_path)._build_prompt(ctx)


# RiskLevelSectionGenerator


class TestRiskLevelSectionGenerator:
    def _gen(self, tmp_path: Path) -> Any:
        return _make_generator(RiskLevelSectionGenerator, tmp_path)

    def test_prompt_contains_risk_level(self, tmp_path: Path) -> None:
        assert "High" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_confirmed_high_count(self, tmp_path: Path) -> None:
        # _HIGH_RISK_COUNTS has confirmed_high=2
        assert "2" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_contains_severity_distribution(self, tmp_path: Path) -> None:
        assert "Critical: 1" in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_prompt_includes_rag_context(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["rag_context"] = "auth bypass vulnerability"
        assert "auth bypass vulnerability" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_omits_rag_block_when_absent(self, tmp_path: Path) -> None:
        assert "semantic search" not in self._gen(tmp_path)._build_prompt(_base_ctx())

    def test_generate_returns_llm_output(self, tmp_path: Path) -> None:
        gen = self._gen(tmp_path)
        with patch.object(gen, "_call_llm", return_value="risk paragraph"):
            assert gen.generate(_base_ctx()) == "risk paragraph"


# CriticalIssuesGenerator


class TestCriticalIssuesGenerator:
    def _gen(self, tmp_path: Path) -> Any:
        return _make_generator(CriticalIssuesGenerator, tmp_path)

    def _ctx_with_findings(self) -> dict:
        ctx = _base_ctx()
        ctx["top_findings"] = [
            _make_finding(
                tal_id="ACM-001",
                severity="critical",
                confidence="confirmed",
                description="SQL injection in login endpoint",
                business_impact="Full database compromise",
                tool="semgrep",
            ),
            _make_finding(
                tal_id="ACM-002",
                severity="high",
                confidence="probable",
                description="Hardcoded credentials in config",
                business_impact="",
                tool="",
            ),
        ]
        return ctx

    def test_prompt_contains_finding_id(self, tmp_path: Path) -> None:
        assert "ACM-001" in self._gen(tmp_path)._build_prompt(self._ctx_with_findings())

    def test_prompt_contains_description(self, tmp_path: Path) -> None:
        assert "SQL injection in login endpoint" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_findings()
        )

    def test_prompt_contains_severity(self, tmp_path: Path) -> None:
        prompt = self._gen(tmp_path)._build_prompt(self._ctx_with_findings())
        assert "Critical" in prompt

    def test_prompt_contains_tool_when_present(self, tmp_path: Path) -> None:
        assert "semgrep" in self._gen(tmp_path)._build_prompt(self._ctx_with_findings())

    def test_prompt_tool_line_only_for_findings_with_tool(self, tmp_path: Path) -> None:
        # ACM-001 has a tool, ACM-002 does not; "Tool:" appears exactly once
        prompt = self._gen(tmp_path)._build_prompt(self._ctx_with_findings())
        assert prompt.count("Tool:") == 1

    def test_prompt_contains_business_impact_when_present(self, tmp_path: Path) -> None:
        assert "Full database compromise" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_findings()
        )

    def test_empty_findings_produces_no_finding_id_lines(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["top_findings"] = []
        assert "Finding ID:" not in self._gen(tmp_path)._build_prompt(ctx)

    def test_fallback_tal_id_when_missing(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["top_findings"] = [
            _make_finding(
                tal_id=None,
                severity="high",
                confidence="confirmed",
                description="Some issue",
            )
        ]
        assert "(no finding ID)" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prefix_used_in_example_id(self, tmp_path: Path) -> None:
        prompt = self._gen(tmp_path)._build_prompt(self._ctx_with_findings())
        assert "ACM-001" in prompt

    def test_prompt_includes_rag_context(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_findings()
        ctx["rag_context"] = "related findings from ChromaDB"
        prompt = self._gen(tmp_path)._build_prompt(ctx)
        assert "related findings from ChromaDB" in prompt

    def test_generate_returns_llm_output(self, tmp_path: Path) -> None:
        gen = self._gen(tmp_path)
        with patch.object(gen, "_call_llm", return_value="critical issues text"):
            assert gen.generate(self._ctx_with_findings()) == "critical issues text"


# ImprovementPointsGenerator


class TestImprovementPointsGenerator:
    def _gen(self, tmp_path: Path) -> Any:
        return _make_generator(ImprovementPointsGenerator, tmp_path)

    def _ctx_with_groups(self) -> dict:
        ctx = _base_ctx()
        ctx["risk_type_groups"] = [
            ("injection", 5),
            ("authentication", 3),
            ("misconfiguration", 1),
        ]
        return ctx

    def test_prompt_contains_risk_type_name(self, tmp_path: Path) -> None:
        assert "injection" in self._gen(tmp_path)._build_prompt(self._ctx_with_groups())

    def test_prompt_contains_occurrence_count(self, tmp_path: Path) -> None:
        assert "5 occurrences" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_groups()
        )

    def test_prompt_uses_singular_when_count_is_one(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["risk_type_groups"] = [("misconfiguration", 1)]
        prompt = self._gen(tmp_path)._build_prompt(ctx)
        assert "1 occurrence)" in prompt
        assert "1 occurrences)" not in prompt

    def test_prompt_empty_groups_shows_fallback(self, tmp_path: Path) -> None:
        ctx = _base_ctx()
        ctx["risk_type_groups"] = []
        assert "(no risk type data available)" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_contains_severity_distribution(self, tmp_path: Path) -> None:
        assert "Critical: 1" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_groups()
        )

    def test_prompt_includes_rag_context(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_groups()
        ctx["rag_context"] = "patterns across findings"
        assert "patterns across findings" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_omits_rag_block_when_absent(self, tmp_path: Path) -> None:
        assert "semantic search" not in self._gen(tmp_path)._build_prompt(
            self._ctx_with_groups()
        )

    def test_generate_returns_llm_output(self, tmp_path: Path) -> None:
        gen = self._gen(tmp_path)
        with patch.object(gen, "_call_llm", return_value="improvement themes"):
            assert gen.generate(self._ctx_with_groups()) == "improvement themes"


# ScopeMethodologyGenerator


class TestScopeMethodologyGenerator:
    def _gen(self, tmp_path: Path) -> Any:
        return _make_generator(ScopeMethodologyGenerator, tmp_path)

    def _ctx_with_scope(self) -> dict:
        ctx = _base_ctx()
        ctx.update(
            {
                "tools": ["semgrep", "gitleaks"],
                "url_hosts": ["example.com"],
                "ecosystems": ["PyPI", "npm"],
                "tools_blurb": "Semgrep performs static analysis.",
            }
        )
        return ctx

    def test_prompt_contains_project_name(self, tmp_path: Path) -> None:
        assert "Acme Corp" in self._gen(tmp_path)._build_prompt(self._ctx_with_scope())

    def test_prompt_contains_tools(self, tmp_path: Path) -> None:
        prompt = self._gen(tmp_path)._build_prompt(self._ctx_with_scope())
        assert "semgrep" in prompt
        assert "gitleaks" in prompt

    def test_prompt_contains_repos(self, tmp_path: Path) -> None:
        assert "acme/backend" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_scope()
        )

    def test_prompt_contains_url_hosts(self, tmp_path: Path) -> None:
        assert "example.com" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_scope()
        )

    def test_prompt_contains_ecosystems(self, tmp_path: Path) -> None:
        assert "PyPI" in self._gen(tmp_path)._build_prompt(self._ctx_with_scope())

    def test_prompt_omits_network_section_when_no_hosts(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_scope()
        ctx["url_hosts"] = []
        prompt = self._gen(tmp_path)._build_prompt(ctx)
        assert "Web endpoints" not in prompt

    def test_prompt_contains_tools_blurb(self, tmp_path: Path) -> None:
        assert "Semgrep performs static analysis." in self._gen(tmp_path)._build_prompt(
            self._ctx_with_scope()
        )

    def test_prompt_empty_repos_shows_none_recorded(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_scope()
        ctx["repos"] = []
        assert "(none recorded)" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_contains_engagement_date(self, tmp_path: Path) -> None:
        assert "2025-06-01" in self._gen(tmp_path)._build_prompt(self._ctx_with_scope())

    def test_generate_returns_llm_output(self, tmp_path: Path) -> None:
        gen = self._gen(tmp_path)
        with patch.object(gen, "_call_llm", return_value="scope section"):
            assert gen.generate(self._ctx_with_scope()) == "scope section"


# GeneralRecommendationsGenerator


class TestGeneralRecommendationsGenerator:
    def _gen(self, tmp_path: Path) -> Any:
        return _make_generator(GeneralRecommendationsGenerator, tmp_path)

    def _ctx_with_recs(self) -> dict:
        ctx = _base_ctx()
        ctx.update(
            {
                "risk_type_groups": [("injection", 4), ("secrets", 2)],
                "recurring_by_risk_type": {
                    "injection": [{"id": 1}, {"id": 2}],
                },
                "improvement_points_draft": None,
            }
        )
        return ctx

    def test_prompt_contains_risk_type_group(self, tmp_path: Path) -> None:
        assert "injection" in self._gen(tmp_path)._build_prompt(self._ctx_with_recs())

    def test_prompt_contains_recurring_count(self, tmp_path: Path) -> None:
        assert "injection: 2 recurring finding(s)" in self._gen(tmp_path)._build_prompt(
            self._ctx_with_recs()
        )

    def test_prompt_empty_groups_shows_fallback(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_recs()
        ctx["risk_type_groups"] = []
        assert "(no risk type data available)" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_empty_recurring_shows_fallback(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_recs()
        ctx["recurring_by_risk_type"] = {}
        assert "(no recurring findings)" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_includes_improvement_draft_when_present(
        self, tmp_path: Path
    ) -> None:
        ctx = self._ctx_with_recs()
        ctx["improvement_points_draft"] = "## Injection patterns\n..."
        prompt = self._gen(tmp_path)._build_prompt(ctx)
        assert "## Injection patterns" in prompt
        assert "complement" in prompt

    def test_prompt_omits_improvement_block_when_none(self, tmp_path: Path) -> None:
        assert "complement" not in self._gen(tmp_path)._build_prompt(
            self._ctx_with_recs()
        )

    def test_prompt_includes_rag_context(self, tmp_path: Path) -> None:
        ctx = self._ctx_with_recs()
        ctx["rag_context"] = "remediation examples"
        assert "remediation examples" in self._gen(tmp_path)._build_prompt(ctx)

    def test_prompt_omits_rag_block_when_absent(self, tmp_path: Path) -> None:
        assert "semantic search" not in self._gen(tmp_path)._build_prompt(
            self._ctx_with_recs()
        )

    def test_generate_returns_llm_output(self, tmp_path: Path) -> None:
        gen = self._gen(tmp_path)
        with patch.object(gen, "_call_llm", return_value="recommendations text"):
            assert gen.generate(self._ctx_with_recs()) == "recommendations text"
