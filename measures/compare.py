"""How a measure changed from one cohort to the next: the rules behind every KPI trend arrow.

Every page that shows a trend calls compare() (for two MeasureResult rows) or compare_values() (for
numbers that aren't a measure, such as a headcount), so everyone reads a change the same way.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Group, MeasureResult, Status

# A relative change smaller than this percent reads as "the same", on every KPI.
SAME_WITHIN_PCT = 1.0


@dataclass(frozen=True)
class TrendRule:
    """Which way is better for one KPI."""

    # True: up is better. False: down is better. None: neither, so the change is never judged.
    higher_is_better: bool | None


# One row per KPI with a trend: the measures by name, plus the cohort profile counts.
TREND_RULES: dict[str, TrendRule] = {
    "retention": TrendRule(higher_is_better=True),
    # Persistence is enrolling at another institution: for a two-year college, going on is success.
    "persistence": TrendRule(higher_is_better=True),
    "gateway_math": TrendRule(higher_is_better=True),
    "gateway_english": TrendRule(higher_is_better=True),
    "fall_to_spring_retention": TrendRule(higher_is_better=True),
    "completion": TrendRule(higher_is_better=True),
    # Graduation within 150% time, from the institution's records (the Playground executive view).
    "graduation": TrendRule(higher_is_better=True),
    "entering_students": TrendRule(higher_is_better=True),
    # A deliberate call: more transfer-in and part-time students reads as a good sign.
    "transfer_in_share": TrendRule(higher_is_better=True),
    "part_time_share": TrendRule(higher_is_better=True),
}


@dataclass(frozen=True)
class Change:
    """A KPI's relative change from the earlier cohort to the latest."""

    relative_pct: float  # (latest - earlier) / earlier * 100, to one decimal
    direction: str  # "up", "down" or "flat"
    judgement: str  # "good", "bad" or "neutral"

    def label(self, previous: str) -> str:
        """The change as every tile and the published trends word it, e.g. '−3.5% vs 2022-23'."""
        sign = "+" if self.relative_pct >= 0 else "−"
        return f"{sign}{abs(self.relative_pct):.1f}% vs {previous}"


def compare_values(name: str, earlier: float | None, latest: float | None) -> Change | None:
    """The change between two numbers for the KPI called name, or None if it can't be worked out."""
    if earlier is None or latest is None or earlier == 0:
        return None
    change = round((latest - earlier) / earlier * 100, 1)
    if abs(change) < SAME_WITHIN_PCT:
        return Change(relative_pct=change, direction="flat", judgement="neutral")
    rose = change > 0
    better = TREND_RULES[name].higher_is_better
    if better is None:
        judgement = "neutral"
    else:
        judgement = "good" if rose == better else "bad"
    return Change(relative_pct=change, direction="up" if rose else "down", judgement=judgement)


def compare(earlier: MeasureResult, latest: MeasureResult) -> Change | None:
    """The change in rate between two rows of one measure, or None when either row is hidden."""
    if earlier.measure != latest.measure:
        raise ValueError("compare needs two rows of the same measure")
    if earlier.status != Status.OK or latest.status != Status.OK:
        return None
    return compare_values(latest.measure.value, earlier.metric_rate, latest.metric_rate)


@dataclass(frozen=True)
class CohortTrend:
    """One published trend: a KPI's change for one group from the previous single cohort to this one."""

    kpi: str  # a measure's name, or entering_students
    cohort: str
    previous_cohort: str
    group: Group
    change: Change
