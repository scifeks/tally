"""Tests for CLI parser mode flags (--interaction-mode, --billing-method, etc)."""

from __future__ import annotations

from application.cli.parser import build_parser


def test_parser_accepts_interaction_mode() -> None:
    """Parser accepts --interaction-mode, --billing-method, --only flags."""
    args = build_parser().parse_args(
        [
            "--project",
            "p",
            "--command",
            "scan",
            "--interaction-mode",
            "background",
            "--billing-method",
            "plan",
            "--only",
            "scan-xss-stored",
        ]
    )
    assert args.interaction_mode == "background"
    assert args.billing_method == "plan"
    assert args.only == "scan-xss-stored"


def test_parser_list_skills_flag() -> None:
    """Parser accepts --list-skills flag."""
    args = build_parser().parse_args(
        [
            "--project",
            "p",
            "--command",
            "scan",
            "--list-skills",
        ]
    )
    assert args.list_skills is True


def test_parser_resume_flag() -> None:
    """Parser accepts --resume flag with run ID."""
    args = build_parser().parse_args(
        [
            "--project",
            "p",
            "--command",
            "scan",
            "--resume",
            "42",
        ]
    )
    assert args.resume == 42
