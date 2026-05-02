"""Risk level formula for report generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    """Overall engagement risk rating."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


@dataclass(frozen=True)
class RiskCounts:
    """Severity/confidence counts required by the risk level formula."""

    confirmed_critical: int
    confirmed_high: int
    prob_confirmed_medium: int
    low_total: int
    recurring: int


def compute_risk_level(counts: RiskCounts) -> RiskLevel:
    """Apply risk level rules in order; return first match.

    Rules (evaluated top-to-bottom, first match wins):
    1. Critical: any confirmed critical or 3+ confirmed high
    2. High: any confirmed high or 5+ probable/confirmed medium
    3. Medium: any probable/confirmed medium or 3+ low
    4. Low: everything else
    """
    if counts.confirmed_critical >= 1 or counts.confirmed_high >= 3:
        return RiskLevel.CRITICAL
    if counts.confirmed_high >= 1 or counts.prob_confirmed_medium >= 5:
        return RiskLevel.HIGH
    if counts.prob_confirmed_medium >= 1 or counts.low_total >= 3:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW
