"""Filter AST equality and structural composition."""

from __future__ import annotations

from application.ports.filters import And, Contains, Eq, Or


class TestFilterAst:
    def test_eq_equality_by_value(self) -> None:
        assert Eq("tool", "semgrep") == Eq("tool", "semgrep")
        assert Eq("tool", "semgrep") != Eq("tool", "gitleaks")
        assert Eq("tool", "semgrep") != Eq("severity", "semgrep")

    def test_eq_supports_scalar_types(self) -> None:
        assert Eq("count", 5).value == 5
        assert Eq("score", 0.75).value == 0.75
        assert Eq("active", True).value is True

    def test_contains_equality_by_value(self) -> None:
        assert Contains("title", "sql") == Contains("title", "sql")
        assert Contains("title", "sql") != Contains("title", "xss")

    def test_and_groups_clauses(self) -> None:
        clause = And(
            clauses=(
                Eq("tool", "semgrep"),
                Eq("severity", "high"),
            )
        )
        assert clause.clauses[0] == Eq("tool", "semgrep")
        assert clause.clauses[1] == Eq("severity", "high")

    def test_or_groups_clauses(self) -> None:
        clause = Or(
            clauses=(
                Eq("severity", "high"),
                Eq("severity", "critical"),
            )
        )
        assert clause.clauses[0] == Eq("severity", "high")
        assert clause.clauses[1] == Eq("severity", "critical")

    def test_nested_and_or_compose(self) -> None:
        clause = And(
            clauses=(
                Eq("tool", "semgrep"),
                Or(
                    clauses=(
                        Eq("severity", "high"),
                        Eq("severity", "critical"),
                    )
                ),
            )
        )
        inner = clause.clauses[1]
        assert isinstance(inner, Or)
        assert inner.clauses[0] == Eq("severity", "high")

    def test_dataclasses_are_frozen(self) -> None:
        import dataclasses

        eq = Eq("tool", "semgrep")
        try:
            eq.value = "gitleaks"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("Eq should be frozen")

    def test_dataclasses_are_hashable(self) -> None:
        clauses = {
            Eq("tool", "semgrep"),
            Eq("tool", "semgrep"),
            Contains("title", "sql"),
        }
        assert len(clauses) == 2
