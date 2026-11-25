"""The five snapshot KPIs, each taken from a measure another Sandbox page already shows.

Enrollment comes from the enrollment trends query. Retention, persistence
(fall_to_spring_retention), transfer out (persistence) and completion are shared measures, and
every arrow uses measures/compare.py on the rates as published, so query_results with include
trends gives the same label.
"""

from functools import cache

from app.sandbox.credential_trends import results as credentials
from app.sandbox.enrollment_trends import kpis as enrollment_kpis
from app.sandbox.enrollment_trends import results as enrollment
from app.sandbox.executive_view import results as executive
from app.sandbox.executive_view.schemas import CohortLens, TrendKpi, TrendKpiResponse
from app.sandbox.shared import ChartMeta

from .schemas import TrendRow, TrendsResponse

MIN_GROUP_SIZE = 10
COMPLETION_YEARS = 3

# An associate or a certificate counts once, even for a student who earned both.
_COMPLETION_SQL = f"""
SELECT cohort, MAX(credit_years_observed) AS years_observed, COUNT(*) AS n,
       SUM(CASE WHEN first_year_to_associates_at_coho BETWEEN 1 AND {COMPLETION_YEARS}
                  OR first_year_to_certificate_at_coh BETWEEN 1 AND {COMPLETION_YEARS}
                THEN 1 ELSE 0 END) AS completed
FROM cohort_membership
GROUP BY cohort
ORDER BY cohort
"""

# Tile order on the page, with each tile's label and the words after "12 of 40".
_TILES = {
    "entering_students": ("Enrollment", ""),
    "retention": ("Retention", "students returned or earned a credential by the next year"),
    "fall_to_spring": ("Persistence", "fall starters were still enrolled in spring"),
    "transfer_out": ("Transfer out", "students went on at another institution by year 2"),
    "completion": (
        "Completion",
        f"students earned an associate or certificate here within {COMPLETION_YEARS} years",
    ),
}

Counts = tuple[int, int]

# The shared measure (and trend rule in measures/compare.py) behind each tile.
_MEASURES = {
    "retention": "retention",
    "fall_to_spring": "fall_to_spring_retention",
    "transfer_out": "persistence",
    "completion": "completion",
}
_RULE_KEYS = {"entering_students": "entering_students", **_MEASURES}
# The tiles whose measure needs year 2, which the partly observed cohort hasn't fully had.
_NEEDS_YEAR_2 = ("retention", "transfer_out")


def _pooled(per_cohort: dict[str, Counts], years: list[str]) -> Counts | None:
    """Add up the (part, whole) counts of the given cohorts, or None if none has any."""
    found = [per_cohort[year] for year in years if year in per_cohort]
    if not found:
        return None
    return sum(part for part, _ in found), sum(whole for _, whole in found)


def _entering_counts() -> dict[str, Counts]:
    """Per cohort: (entering, entering)."""
    return {
        cohort: (total, total)
        for cohort, total in enrollment._fetch(enrollment_kpis._COHORT_COUNTS_SQL)
    }


def _completion_counts() -> tuple[dict[str, Counts], set[str]]:
    """Per cohort: (completed, students), and the cohorts that have had every counted year."""
    counts = {}
    observed = set()
    for cohort, years_observed, n, completed in credentials._fetch(_COMPLETION_SQL):
        counts[cohort] = (int(completed), n)
        full = credentials._full_years(years_observed)
        if full is not None and full >= COMPLETION_YEARS:
            observed.add(cohort)
    return counts, observed


def _measure_counts(name: str, years: list[str]) -> Counts | None:
    """A shared measure's (numerator, denominator) for the given cohorts pooled."""
    return executive.measure_counts(name, years)


def _rate(counts: Counts | None) -> float | None:
    """Part as a 0-to-1 rate rounded as published, or None when the group is too small to show."""
    if counts is None or counts[1] < MIN_GROUP_SIZE:
        return None
    return executive.measure_rate(counts)


def _tile(name: str, latest: Counts, earlier: Counts | None, previous_year: str | None) -> TrendKpi:
    """One KPI tile, with its trend against the previous cohort when there is one."""
    label, outcome = _TILES[name]
    trend = None
    if previous_year is not None and earlier is not None:
        before, now = _rate(earlier), _rate(latest)
        if name == "entering_students":
            # A count compares as itself, still hidden under the display threshold.
            before = float(earlier[0]) if earlier[0] >= MIN_GROUP_SIZE else None
            now = float(latest[0])
        trend = executive._trend(_RULE_KEYS[name], before, now, previous_year)

    if name == "entering_students":
        return TrendKpi(
            id=name,
            label=label,
            unit="count",
            value=latest[0],
            detail="Students in the entering cohorts shown",
            trend=trend,
        )
    return TrendKpi(
        id=name,
        label=label,
        unit="percent",
        value=executive._percent(executive.measure_rate(latest)),
        detail=f"{latest[0]:,} of {latest[1]:,} {outcome}",
        trend=trend,
    )


def _all_counts(years: list[str]) -> dict[str, Counts | None]:
    """Every tile's counts for one set of cohorts, keyed like _TILES."""
    counts: dict[str, Counts | None] = {"entering_students": _pooled(_entering_counts(), years)}
    for name, measure in _MEASURES.items():
        counts[name] = _measure_counts(measure, years)
    return counts


def _observed_completion_tile() -> TrendKpi | None:
    """The completion tile pooled over only the cohorts that have had the full window."""
    _, observed = _completion_counts()
    years = [year for year in executive._COHORT_YEARS if year in observed]
    counts = _measure_counts("completion", years) if years else None
    if counts is None or counts[1] < MIN_GROUP_SIZE:
        return None
    tile = _tile("completion", counts, None, None)
    tile.detail += f" (cohorts {', '.join(years)} only)"
    return tile


def _partial_completion_tile(counts: Counts | None) -> TrendKpi | None:
    """The completion tile for one cohort still inside its window: the count so far, no trend."""
    if counts is None or counts[1] < MIN_GROUP_SIZE:
        return None
    tile = _tile("completion", counts, None, None)
    tile.detail += f" so far; the {COMPLETION_YEARS}-year window isn't over yet"
    return tile


def _short_of_year_2(name: str, cohort: str) -> bool:
    """Whether a tile's measure needs a year 2 that this single cohort hasn't fully had yet."""
    return name in _NEEDS_YEAR_2 and cohort == executive._PARTLY_OBSERVED


def _partial_year_2_tile(name: str, counts: Counts) -> TrendKpi:
    """A retention or transfer out tile for a cohort short of year 2: the share so far, no trend."""
    tile = _tile(name, counts, None, None)
    tile.detail += "; year 2 isn't fully observed yet, so this will likely rise"
    return tile


@cache
def kpi_definitions() -> dict[str, str]:
    """What each snapshot tile counts, by label: the tiles' tooltips, and the chat's definition."""
    return {
        # Retention is a shared measure, so its wording comes from the measure itself
        # rather than a second copy that can drift from the published results.
        "Retention": executive.measure_definitions()["Retention"],
        "Enrollment": (
            "Students who entered in the cohorts shown. The count everything else on this "
            "card is measured against."
        ),
        "Persistence": "Fall starters still enrolled in the spring after their first fall.",
        "Transfer out": (
            "The PDP persistence flag: enrolled at, or earned a credential from, "
            "another institution by year 2."
        ),
        "Completion": (
            f"An associate or certificate from this college within {COMPLETION_YEARS} "
            "years of entry."
        ),
    }


def get_kpis(cohort: CohortLens) -> TrendKpiResponse:
    """Calculate the five snapshot KPIs for one cohort or all pooled, with trends where fair."""
    years = executive._years_for(cohort)
    previous_year = executive._previous_year(cohort)
    latest = _all_counts(years)
    earlier = _all_counts([previous_year]) if previous_year else {}
    completion_so_far, completion_observed = _completion_counts()
    items = []
    for name in _TILES:
        # The measure hides a cohort short of its completion window. Show the count so far
        # instead, with no arrow: a partial window against a full one would read as a drop.
        if name == "completion" and cohort != "all" and cohort not in completion_observed:
            tile = _partial_completion_tile(completion_so_far.get(cohort))
            if tile is not None:
                items.append(tile)
            continue
        counts = latest[name]
        if counts is None or counts[1] < MIN_GROUP_SIZE:
            continue
        # Likewise a cohort short of year 2: a partial year against a full one reads as a drop.
        if _short_of_year_2(name, cohort):
            items.append(_partial_year_2_tile(name, counts))
            continue
        items.append(_tile(name, counts, earlier.get(name), previous_year))

    # The measure hides completion for a pool with any cohort short of its window, so the pooled
    # view counts only the cohorts that have had the full window.
    if cohort == "all" and latest["completion"] is None:
        tile = _observed_completion_tile()
        if tile is not None:
            items.append(tile)

    filters = executive._cohort_filters(cohort)
    if previous_year is not None:
        filters += [f"Arrows: relative change vs {previous_year}", executive._same_band_filter()]

    return TrendKpiResponse(
        meta=ChartMeta(
            title="Student success snapshot",
            description=(
                "Enrollment, retention, persistence, transfer and completion for the selected "
                "entering cohorts."
            ),
            fields_used=[
                "Cohort",
                "Retention",
                "Persistence",
                "Academic term",
                "First year to associates",
                "First year to certificate",
            ],
            filters=[*filters, "Synthetic data, not real students"],
            definitions=kpi_definitions(),
            source="synthetic",
        ),
        items=items,
    )


def _trend_row(name: str, cohort: str, counts: Counts | None, partial: bool) -> TrendRow:
    """One cohort's point on one metric's trend line, hidden under the display threshold."""
    label, _ = _TILES[name]
    unit = "count" if name == "entering_students" else "percent"
    if counts is None or counts[1] < MIN_GROUP_SIZE:
        return TrendRow(
            metric=name,
            label=label,
            unit=unit,
            cohort=cohort,
            value=None,
            numerator=None,
            n=None,
            partial=partial,
        )
    value = (
        float(counts[0]) if unit == "count" else executive._percent(executive.measure_rate(counts))
    )
    return TrendRow(
        metric=name,
        label=label,
        unit=unit,
        cohort=cohort,
        value=value,
        numerator=int(counts[0]),
        n=int(counts[1]),
        partial=partial,
    )


def get_trends() -> TrendsResponse:
    """Each of the five metrics for every entering cohort, for trend lines."""
    completion_so_far, completion_observed = _completion_counts()
    rows = []
    for year in executive._COHORT_YEARS:
        counts = _all_counts([year])
        for name in _TILES:
            # Retention and transfer need year 2; completion needs its full window.
            if name == "completion":
                partial = year not in completion_observed
                # The measure hides a partial window, so draw the count so far (dashed).
                if partial:
                    counts[name] = completion_so_far.get(year)
            else:
                partial = _short_of_year_2(name, year)
            rows.append(_trend_row(name, year, counts[name], partial))

    return TrendsResponse(
        meta=ChartMeta(
            title="Student success trends",
            description="The five student success metrics for each entering cohort, oldest first.",
            takeaway=(
                "Dashed points are cohorts not yet fully observed, so they will likely rise "
                "as more terms come in."
            ),
            fields_used=[
                "Cohort",
                "Retention",
                "Persistence",
                "Academic term",
                "First year to associates",
                "First year to certificate",
            ],
            filters=["Every entering cohort", "Synthetic data, not real students"],
            definitions={
                "Enrollment": "Students in each entering cohort.",
                "Retention": "Returned here or earned a credential by the next year.",
                "Persistence": "Fall starters still enrolled in the spring after their first fall.",
                "Transfer out": (
                    "Enrolled at, or earned a credential from, another institution by year 2."
                ),
                "Completion": (
                    f"An associate or certificate from this college within {COMPLETION_YEARS} "
                    "years of entry."
                ),
            },
            source="synthetic",
        ),
        rows=rows,
    )
