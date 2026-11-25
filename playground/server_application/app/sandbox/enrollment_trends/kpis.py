"""Headline enrollment KPIs: the latest entering cohort, each compared with the one before.

The shares are the shared make-up measures (transfer_in_share, part_time_share) and first fall to
spring is fall_to_spring_retention, each run live. Every arrow compares the rates as they are
published, so query_results with include trends gives the same label.
"""

from app.sandbox.executive_view import results as executive
from app.sandbox.executive_view.results import _same_band_filter, _trend
from app.sandbox.executive_view.schemas import KpiTrend, TrendKpi, TrendKpiResponse
from app.sandbox.shared import ChartMeta

from . import results

_COHORT_COUNTS_SQL = """
SELECT cohort, COUNT(DISTINCT student_id) AS entering
FROM cohort_membership
GROUP BY cohort
ORDER BY cohort
"""

# Each tile's label, and the words after "12 of 40" in its detail line.
_SHARE_TILES = {
    "transfer_share": ("Transfer-in share", "entering students came in as transfers"),
    "part_time_share": ("Part-time at entry", "entering students started part-time"),
    "fall_to_spring": ("First fall to spring", "fall starters were still enrolled in spring"),
}

# The shared measure behind each share tile, which is also its rule in measures/compare.py.
_MEASURES = {
    "transfer_share": "transfer_in_share",
    "part_time_share": "part_time_share",
    "fall_to_spring": "fall_to_spring_retention",
}
_RULE_KEYS = {"entering_students": "entering_students", **_MEASURES}


def _trend_vs(name: str, earlier: float | None, latest: float, year: str | None) -> KpiTrend | None:
    """The change from the earlier cohort, or None when there isn't one to compare with."""
    return None if year is None else _trend(_RULE_KEYS[name], earlier, latest, year)


def _measure_counts(name: str, cohorts: list[str]) -> dict[str, tuple[int, int]]:
    """Per cohort: a shared measure's (numerator, denominator), leaving out cohorts it hides."""
    counts = {}
    for cohort in cohorts:
        found = executive.measure_counts(name, [cohort])
        if found is not None:
            counts[cohort] = found
    return counts


def _fall_to_spring_counts(cohorts: list[str]) -> dict[str, tuple[int, int]]:
    """Per cohort: the shared fall_to_spring_retention measure's (retained, fall starters)."""
    return _measure_counts("fall_to_spring_retention", cohorts)


def _share_counts(name: str, cohorts: list[str]) -> dict[str, tuple[int, int]]:
    """Per cohort: a make-up measure's (students, entering students), e.g. transfer_in_share's."""
    return _measure_counts(_MEASURES[name], cohorts)


def _shown_rate(counts: tuple[int, int] | None) -> float | None:
    """The rate as published, or None when either count is too small to show."""
    if counts is None or min(counts) < results.MIN_GROUP_SIZE:
        return None
    return executive.measure_rate(counts)


def _empty_response() -> TrendKpiResponse:
    """The response when no data model rows exist."""
    return TrendKpiResponse(
        meta=ChartMeta(
            title="Latest entering cohort",
            description="No cohorts are loaded.",
            fields_used=[],
            filters=[],
            source="synthetic",
        ),
        items=[],
    )


def get_kpis() -> TrendKpiResponse:
    """Calculate the latest cohort's enrollment KPIs, each with its change from the one before."""
    entering = {cohort: total for cohort, total in results._fetch(_COHORT_COUNTS_SQL)}

    cohorts = sorted(entering)
    if not cohorts:
        return _empty_response()
    latest = cohorts[-1]
    earlier = cohorts[-2] if len(cohorts) > 1 else None
    compared = [c for c in (earlier, latest) if c]
    shares = {
        "transfer_share": _share_counts("transfer_share", compared),
        "part_time_share": _share_counts("part_time_share", compared),
        "fall_to_spring": _fall_to_spring_counts(compared),
    }

    items = []
    if entering[latest] >= results.MIN_GROUP_SIZE:
        before = entering.get(earlier) if earlier else None
        shown_before = float(before) if before and before >= results.MIN_GROUP_SIZE else None
        items.append(
            TrendKpi(
                id="entering_students",
                label="Entering students",
                unit="count",
                value=entering[latest],
                detail=f"Students in the {latest} entering cohort",
                trend=_trend_vs("entering_students", shown_before, entering[latest], earlier),
            )
        )

    for name, (label, outcome) in _SHARE_TILES.items():
        counts = shares[name].get(latest)
        share = _shown_rate(counts)
        if counts is None or share is None:
            continue
        before_share = _shown_rate(shares[name].get(earlier)) if earlier else None
        items.append(
            TrendKpi(
                id=name,
                label=label,
                unit="percent",
                value=executive._percent(share),
                detail=f"{counts[0]:,} of {counts[1]:,} {outcome}",
                trend=_trend_vs(name, before_share, share, earlier),
            )
        )

    filters = [f"{latest} cohort"]
    if earlier is not None:
        filters += [f"Arrows: relative change vs {earlier}", _same_band_filter()]

    return TrendKpiResponse(
        meta=ChartMeta(
            title="Latest entering cohort",
            description="Who the newest cohort is, and how many carried on from fall to spring.",
            fields_used=["Cohort", "Enrollment type", "First-term intensity", "Academic term"],
            filters=[*filters, "Synthetic data, not real students"],
            source="synthetic",
        ),
        items=items,
    )
