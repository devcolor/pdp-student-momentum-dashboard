"""Student Success & Equity Analysis: population, programs and credit momentum by one equity group.

Retention gaps come from the shared gap finder. Group sizes, program splits and year-1 credit
milestones are plain counts from the data model, with groups under 10 students hidden, and covered
across the pool and its years (executive_view/small_counts.py, hide_across_lenses).
"""

from typing import Any

from app.sandbox.credential_trends import results as credentials
from app.sandbox.executive_view import cohorts
from app.sandbox.executive_view import results as executive
from app.sandbox.executive_view.schemas import CohortLens
from app.sandbox.executive_view.small_counts import hide_across_lenses
from app.sandbox.shared import ChartMeta

from . import results
from .schemas import (
    EquityDimension,
    EquityGroup,
    EquityProgram,
    EquityResponse,
    ProgramSegment,
)

MIN_GROUP_SIZE = 10
TOP_PROGRAMS = 8
CREDIT_MILESTONES = (12, 15, 30)

# Column expressions come only from this table, never from the request.
_DIMENSION_COLUMNS: dict[EquityDimension, str] = {
    "race": "s.race",
    "gender": "s.gender",
    "age_band": "s.student_age",
    "first_gen": "s.first_gen",
    "pell": "cm.pell_status_first_year",
}

DIMENSION_TITLES: dict[EquityDimension, str] = {
    "race": "Race/ethnicity",
    "gender": "Gender",
    "age_band": "Age group",
    "first_gen": "First generation",
    "pell": "Pell status",
}

_VALUE_LABELS: dict[EquityDimension, dict[str, str]] = {
    "gender": {"F": "Female", "M": "Male", "X": "Gender X"},
    "age_band": {"20 and younger": "20 and younger", ">20 - 24": "Over 20, up to 24"},
    "first_gen": {"Y": "First generation", "N": "Not first generation"},
    "pell": {"Y": "Pell", "N": "No Pell"},
}

# Codes the data model uses for "we don't know".
_UNKNOWN_CODES = {None, "", "UNKNOWN", "UK", "U"}
UNKNOWN_LABEL = "Unknown"

_GROUP_SQL = """
SELECT {column} AS grp,
       COUNT(*) AS n,
       {milestones}
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
WHERE cm.cohort IN ({cohorts})
GROUP BY 1
"""

_PROGRAM_SQL = """
SELECT cm.program_of_study_year_1 AS program, {column} AS grp, COUNT(*) AS n
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
WHERE cm.cohort IN ({cohorts})
  AND cm.program_of_study_year_1 IS NOT NULL AND cm.program_of_study_year_1 != ''
GROUP BY 1, 2
"""


def _label(dimension: EquityDimension, value: Any) -> str:
    """A plain name for a group value; unknown codes all read as "Unknown"."""
    if value in _UNKNOWN_CODES:
        return UNKNOWN_LABEL
    return _VALUE_LABELS.get(dimension, {}).get(str(value), str(value))


def _pct(part: int, whole: int) -> float:
    """Part as a percent of whole, to one decimal."""
    return round(part / whole * 100, 1)


def _milestone_sql() -> str:
    """One SUM per credit milestone, e.g. earned_12."""
    return ",\n       ".join(
        f"SUM(CASE WHEN cm.number_of_credits_earned_yr_1 >= {credits} THEN 1 ELSE 0 END) "
        f"AS earned_{credits}"
        for credits in CREDIT_MILESTONES
    )


def _group_counts(dimension: EquityDimension, years: list[str]) -> dict[str, list[int]]:
    """Per group label: [students, earned 12, earned 15, earned 30], unknown codes merged."""
    sql = _GROUP_SQL.format(
        column=_DIMENSION_COLUMNS[dimension],
        milestones=_milestone_sql(),
        cohorts=credentials._placeholders(len(years)),
    )
    counts: dict[str, list[int]] = {}
    for value, *numbers in credentials._fetch(sql, years):
        totals = counts.setdefault(_label(dimension, value), [0] * (1 + len(CREDIT_MILESTONES)))
        for index, number in enumerate(numbers):
            totals[index] += int(number or 0)
    return counts


def _retention_gaps(dimension: EquityDimension, years: list[str]) -> dict[str, Any]:
    """The gap finder's retention row for each group label, from one run over these cohorts."""
    if dimension == "first_gen":
        # The gap finder leaves first_gen out until the data quality finding is
        # settled: its Y reads as UNKNOWN.
        return {}
    find_gaps, _, _ = executive._shared()
    with executive._model_connection() as connection:
        gaps = find_gaps.find_gaps(
            measures=["retention"], cohorts=[years], group_by=[[dimension]], database=connection
        )
    return {
        _label(dimension, gap.group_values[0]): gap
        for gap in gaps
        if len(gap.group_dimensions) == 1 and gap.status == "ok"
    }


def _milestone_rates(numbers: list[int], n: int, shown: bool = True) -> list[float | None]:
    """Each milestone's share of the group, hidden when the group is too small or hidden."""
    if not shown or n < MIN_GROUP_SIZE:
        return [None] * len(CREDIT_MILESTONES)
    return [_pct(count, n) for count in numbers]


def _sizes(counts: dict[str, list[int]]) -> dict[str, int]:
    """Each group's number of students, from its group counts."""
    return {label: numbers[0] for label, numbers in counts.items()}


def _groups(
    dimension: EquityDimension, cohort: CohortLens
) -> tuple[list[EquityGroup], EquityGroup]:
    """Every group's size, retention gap and credit milestones, biggest first, and everyone.

    A group's size is hidden across the pool and its years, and a hidden group shows nothing else.
    """
    years = cohorts.years_for(cohort)
    by_lens = {
        lens: _group_counts(dimension, cohorts.years_for(lens))
        for lens in cohorts.lenses_with(cohort)
    }
    counts = by_lens[cohort]
    hidden = hide_across_lenses({lens: _sizes(each) for lens, each in by_lens.items()})[cohort]
    gaps = _retention_gaps(dimension, years)
    total = sum(numbers[0] for numbers in counts.values())

    groups = []
    for label, (n, *milestones) in counts.items():
        gap = gaps.get(label)
        shown = label not in hidden
        groups.append(
            EquityGroup(
                group=label,
                n=n if shown else None,
                share=_pct(n, total) if shown else None,
                retention=_pct(gap.numerator, gap.denominator) if gap and shown else None,
                retention_gap_pts=round(gap.gap_pts, 1) if gap and shown else None,
                likely_noise=bool(gap.likely_noise) if gap and shown else None,
                milestones=_milestone_rates(milestones, n, shown),
            )
        )
    # Unknown sorts last, so the named groups lead the chart.
    groups.sort(key=lambda group: (group.group == UNKNOWN_LABEL, -(group.n or 0)))

    everyone_milestones = [
        sum(numbers[index + 1] for numbers in counts.values()) for index in range(3)
    ]
    retention = results._measure_counts("retention", years)
    everyone = EquityGroup(
        group="Everyone",
        n=total,
        share=100.0,
        retention=_pct(*retention) if retention else None,
        retention_gap_pts=None,
        likely_noise=None,
        milestones=_milestone_rates(everyone_milestones, total),
    )
    return groups, everyone


def _program_counts(dimension: EquityDimension, years: list[str]) -> dict[str, dict[str, int]]:
    """Per program code: each group label's students, unknown codes merged."""
    sql = _PROGRAM_SQL.format(
        column=_DIMENSION_COLUMNS[dimension], cohorts=credentials._placeholders(len(years))
    )
    by_program: dict[str, dict[str, int]] = {}
    for program, value, n in credentials._fetch(sql, years):
        cells = by_program.setdefault(str(program), {})
        label = _label(dimension, value)
        cells[label] = cells.get(label, 0) + int(n)
    return by_program


def _programs(
    dimension: EquityDimension, cohort: CohortLens, order: list[str]
) -> list[EquityProgram]:
    """The biggest programs, each split by the dimension's groups, small cells hidden.

    Each program's cells are hidden across the pool and its years, like the groups.
    """
    by_lens = {
        lens: _program_counts(dimension, cohorts.years_for(lens))
        for lens in cohorts.lenses_with(cohort)
    }
    biggest = sorted(by_lens[cohort].items(), key=lambda item: -sum(item[1].values()))
    programs = []
    for code, cells in biggest:
        n = sum(cells.values())
        if n < MIN_GROUP_SIZE or len(programs) == TOP_PROGRAMS:
            continue
        segments = {lens: each.get(code, {}) for lens, each in by_lens.items()}
        hidden = hide_across_lenses(segments)[cohort]
        programs.append(
            EquityProgram(
                code=code,
                label=credentials._program_label(code),
                n=n,
                segments=[
                    ProgramSegment(group=group, n=None if group in hidden else cells[group])
                    for group in order
                    if cells.get(group, 0) > 0
                ],
            )
        )
    return programs


def _takeaway(dimension: EquityDimension, groups: list[EquityGroup]) -> str | None:
    """One sentence naming the group furthest behind on retention, if any is clearly behind."""
    if dimension == "first_gen":
        return (
            "Retention gaps by first generation wait on a data quality finding. "
            "Size and credits are shown."
        )
    behind = [
        group
        for group in groups
        if group.retention_gap_pts is not None
        and group.retention_gap_pts < 0
        and not group.likely_noise
        and group.group != UNKNOWN_LABEL
    ]
    if not behind:
        return f"No {DIMENSION_TITLES[dimension].lower()} group is clearly behind on retention."
    worst = min(behind, key=lambda group: group.retention_gap_pts or 0)
    return (
        f"{worst.group} students retain {abs(worst.retention_gap_pts or 0):.1f} points below "
        "everyone else. A gap shows a difference between groups, not its cause."
    )


def get_equity(cohort: CohortLens, dimension: EquityDimension) -> EquityResponse:
    """Population, programs and credit momentum for one cohort lens, split by one equity group."""
    groups, everyone = _groups(dimension, cohort)
    programs = _programs(dimension, cohort, [group.group for group in groups])
    title = DIMENSION_TITLES[dimension]

    return EquityResponse(
        meta=ChartMeta(
            title="Student Success & Equity Analysis",
            description=(
                "Who the students are, where they enroll, and how fast they earn credits, "
                f"by {title.lower()}."
            ),
            takeaway=_takeaway(dimension, groups),
            fields_used=[
                title,
                "Cohort",
                "Retention",
                "Program of study year 1",
                "Number of credits earned year 1",
            ],
            filters=[*executive._cohort_filters(cohort), "Synthetic data, not real students"],
            definitions={
                "Retention gap": (
                    "The group's retention minus everyone else's, in points, from the shared gap "
                    "finder. Gaps likely to be noise are marked."
                ),
                "Programs": f"The {TOP_PROGRAMS} largest year-1 programs of study.",
                "Credit momentum": "Students who earned at least 12, 15 or 30 credits in year 1.",
                "First generation": (
                    "No retention gap yet: the shared gap finder leaves first generation out "
                    "until a data quality finding is settled."
                ),
                "Hidden": (
                    f"Groups and cells under {MIN_GROUP_SIZE} students are not shown. When exactly "
                    "one is hidden, the next-smallest is too, so it can't be worked out from the "
                    "total, or from the pooled cohorts minus the other years."
                ),
            },
            source="synthetic",
        ),
        milestones=[f"{credits}+ credits" for credits in CREDIT_MILESTONES],
        groups=groups,
        everyone=everyone,
        programs=programs,
    )
