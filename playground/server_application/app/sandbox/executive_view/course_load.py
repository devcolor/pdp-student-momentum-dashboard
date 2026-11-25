"""Course load in year 1: the share of students at each level of credits attempted.

One curve for everyone in the cohort, and one for the students who match the filters. Filters
narrow the students down instead of splitting them, so the chart never has more than two curves.
Counts come straight from the data model.
"""

import statistics
from collections import Counter
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.credential_trends.results import _program_label as program_label
from app.sandbox.shared import ChartMeta

# By module, so a patch of cohorts.withholds_live_filters reaches it ("cohorts" is a local here).
from . import cohorts as lenses
from .cohorts import lens_label, years_for
from .schemas import (
    CohortLens,
    CourseLoadFilters,
    CourseLoadResponse,
    Granularity,
    LoadCurve,
    ProgramOption,
)

MIN_GROUP_SIZE = 10
MAX_ROWS = 5000
TIMEOUT_SECONDS = 10.0
# Why the matching curve is blank on a single year inside the pool (cohorts.withholds_live_filters).
POOL_YEAR_HIDDEN = (
    "On a single cohort inside the pool, filters show on the pooled cohorts and 2024-25: these "
    "students could be worked out from the pool minus the other years."
)

# Most courses are 3 credits, so single credit values jump up and down. Bands of 3 read as a curve
# and are the default; the reader can pick every credit, or bands of 6.
BAND_WIDTHS = {"1": 1, "3": 3, "6": 6}
TOP_BAND_START = 36  # Everything from 36 up is one band: the tail is sparse.
UNDER_CREDITS = 12
# 30 credits a year finishes a 60-credit associate in 2 years. The 60 is an assumption, as on the
# associate momentum page.
ON_TRACK_CREDITS = 30

# The goal codes are the credential trends page's.
_GOALS = "('A', 'C1', 'C2', 'C4', '01')"

# Fixed SQL for each filter value, so nothing from the request is written into a query. The one
# exception, a program code, is checked as six digits and passed as a parameter.
_CONDITIONS: dict[str, dict[str, str]] = {
    "goal": {
        "associate": "cm.credential_type_sought_year_1 = 'A'",
        "certificate": "cm.credential_type_sought_year_1 IN ('C1', 'C2', 'C4', '01')",
        "other": (
            "(cm.credential_type_sought_year_1 IS NULL "
            f"OR cm.credential_type_sought_year_1 NOT IN {_GOALS})"
        ),
    },
    "race": {
        "white": "s.race = 'White'",
        "hispanic": "s.race = 'Hispanic'",
        "black": "s.race = 'Black or African American'",
        "asian": "s.race = 'Asian'",
        "two_or_more": "s.race = 'Two or More Races'",
        "nonresident": "s.race = 'Nonresident alien'",
        "american_indian": "s.race = 'American Indian or Alaska Native'",
        "pacific_islander": "s.race = 'Native Hawaiian or Other Pacific Islander'",
        "unknown": "(s.race IS NULL OR s.race = 'UNKNOWN')",
    },
    "gender": {
        "female": "s.gender = 'F'",
        "male": "s.gender = 'M'",
        "x": "s.gender = 'X'",
        "unknown": "(s.gender IS NULL OR s.gender = 'UNKNOWN')",
    },
    "age": {
        "20_and_younger": "s.student_age = '20 and younger'",
        "over_20_to_24": "s.student_age = '>20 - 24'",
        "over_24": "s.student_age = 'Older than 24'",
        "unknown": "(s.student_age IS NULL OR s.student_age = 'UNKNOWN')",
    },
    "pell": {
        "yes": "cm.pell_status_first_year = 'Y'",
        "no": "cm.pell_status_first_year = 'N'",
        "unknown": (
            "(cm.pell_status_first_year IS NULL OR cm.pell_status_first_year IN ('U', 'UNKNOWN'))"
        ),
    },
    "first_gen": {
        "yes": "s.first_gen = 'Y'",
        "no": "s.first_gen = 'N'",
        "not_reported": "(s.first_gen IS NULL OR s.first_gen = 'UNKNOWN')",
    },
}
# Affinity lives in student_attribute, one row per student (synthetic, see affinity_mapping.yaml).
_AFFINITY_NAMES = {
    "none": "None",
    "band": "Band",
    "choir": "Choir",
    "theater": "Theater",
    "football": "Football",
    "baseball": "Baseball",
    "basketball": "Basketball",
    "volleyball": "Volleyball",
    "soccer": "Soccer",
    "student_government": "Student Government",
    "esports": "Esports",
}
_CONDITIONS["affinity"] = {
    value: (
        "EXISTS (SELECT 1 FROM student_attribute af WHERE af.student_id = cm.student_id "
        f"AND af.attribute_key = 'affinity' AND af.attribute_value = '{name}')"
    )
    for value, name in _AFFINITY_NAMES.items()
}
_NO_PROGRAM = "(cm.program_of_study_year_1 IS NULL OR cm.program_of_study_year_1 = '')"

# How each active filter reads in the chart's filter list.
_LABELS: dict[str, tuple[str, dict[str, str]]] = {
    "goal": (
        "Goal",
        {
            "associate": "Associate-seekers",
            "certificate": "Certificate-seekers",
            "other": "Other or unknown goal",
        },
    ),
    "race": (
        "Race",
        {
            "white": "White",
            "hispanic": "Hispanic",
            "black": "Black or African American",
            "asian": "Asian",
            "two_or_more": "Two or More Races",
            "nonresident": "Nonresident alien",
            "american_indian": "American Indian or Alaska Native",
            "pacific_islander": "Native Hawaiian or Other Pacific Islander",
            "unknown": "Unknown",
        },
    ),
    "gender": (
        "Gender",
        {"female": "Female", "male": "Male", "x": "Gender X", "unknown": "Unknown"},
    ),
    "age": (
        "Age",
        {
            "20_and_younger": "20 and younger",
            "over_20_to_24": "Over 20, up to 24",
            "over_24": "Over 24",
            "unknown": "Unknown",
        },
    ),
    "pell": ("Pell", {"yes": "Pell", "no": "No Pell", "unknown": "Unknown"}),
    "first_gen": (
        "First generation",
        {"yes": "First generation", "no": "Not first generation", "not_reported": "Not reported"},
    ),
    "affinity": ("Affinity group", {**_AFFINITY_NAMES, "none": "No group"}),
}

_FIELDS = {
    "goal": "Credential Type Sought Year 1",
    "program": "Program of Study Year 1",
    "race": "Race",
    "gender": "Gender",
    "age": "Student Age",
    "pell": "Pell Status First Year",
    "first_gen": "First Gen",
    "affinity": "Affinity group (synthetic)",
}

_COUNTS = """
SELECT cm.number_of_credits_attempted_yr_1 AS credits, COUNT(*) AS students
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
WHERE cm.cohort IN ({cohorts}) AND cm.number_of_credits_attempted_yr_1 > 0{filters}
GROUP BY 1
"""

# Students with credits by one filter's values, for checking whether a value needs a cover.
_COUNTS_BY_VALUE = """
SELECT {value} AS value, COUNT(*) AS students
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
WHERE cm.cohort IN ({cohorts}) AND cm.number_of_credits_attempted_yr_1 > 0{filters}
GROUP BY 1
"""

_PROGRAMS = """
SELECT cm.program_of_study_year_1, COUNT(*) AS students
FROM cohort_membership cm
WHERE cm.cohort IN ({cohorts}) AND cm.number_of_credits_attempted_yr_1 > 0
  AND cm.program_of_study_year_1 IS NOT NULL AND cm.program_of_study_year_1 != ''
GROUP BY 1
HAVING COUNT(*) >= {min_size}
ORDER BY 2 DESC, 1
"""

_LEFT_OUT = """
SELECT COUNT(*) FROM cohort_membership cm
WHERE cm.cohort IN ({cohorts})
  AND (cm.number_of_credits_attempted_yr_1 IS NULL OR cm.number_of_credits_attempted_yr_1 <= 0)
"""


def band_labels(width: int) -> list[str]:
    """The credit bands in order, e.g. "0-2", "3-5" and so on for width 3, then "36+"."""
    starts = range(0, TOP_BAND_START, width)
    labels = [str(low) if width == 1 else f"{low}-{low + width - 1}" for low in starts]
    return [*labels, f"{TOP_BAND_START}+"]


def _band_index(credits: float, width: int) -> int:
    """Which band a credit count falls in."""
    return min(int(credits // width), TOP_BAND_START // width)


def _fetch(sql: str, params: list[str]) -> list[list[Any]]:
    """Run one fixed read-only query, turning any database problem into a clear 503."""
    db, _, _ = query_tool._mcp()
    try:
        result = query_tool.backend().execute(sql, params, MAX_ROWS, TIMEOUT_SECONDS)
    except (db.Unavailable, db.Failed, db.TimedOut) as exc:
        detail = f"The data model couldn't be read: {exc}. Load it from the Sandbox pipeline page."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from None
    if result.truncated:
        detail = f"The query returned more than {MAX_ROWS} rows, so the counts would be incomplete."
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)
    return result.rows


def _marker() -> str:
    """The query placeholder the backend expects: "?" for SQLite, "%s" for PostgreSQL."""
    return "?" if query_tool.backend().param_style == "qmark" else "%s"


def _percent(part: int, whole: int) -> float:
    """Part as a percent of whole, to one decimal."""
    return round(part / whole * 100, 1)


def _shown_percent(count: int, total: int) -> float | None:
    """The percent, or None when it would let a count under 10 be worked out, on either side."""
    if count < MIN_GROUP_SIZE or total - count < MIN_GROUP_SIZE:
        return None
    return _percent(count, total)


def _band_shares(band_counts: list[int], n: int) -> list[float | None]:
    """Each band's percent of the group. Bands of 1 to 9 students are hidden."""
    hidden = [i for i, count in enumerate(band_counts) if 0 < count < MIN_GROUP_SIZE]
    if len(hidden) == 1:
        # A lone hidden band could be worked out from the total, so hide the next-smallest too.
        shown = [i for i, count in enumerate(band_counts) if count >= MIN_GROUP_SIZE]
        if shown:
            hidden.append(min(shown, key=lambda i: band_counts[i]))
    return [None if i in hidden else _percent(count, n) for i, count in enumerate(band_counts)]


def _hidden_curve(group: str, width: int) -> LoadCurve:
    """A curve with every number blank, for a group that can't be shown."""
    return LoadCurve(
        group=group,
        n=None,
        median_credits=None,
        under_12_pct=None,
        on_track_pct=None,
        shares=[None] * len(band_labels(width)),
    )


def _curve(group: str, counts: Counter[float], width: int) -> LoadCurve:
    """One group's curve and summary, from how many students attempted each credit count."""
    n = sum(counts.values())
    if n < MIN_GROUP_SIZE:
        return _hidden_curve(group, width)
    band_counts = [0] * len(band_labels(width))
    for credits, count in counts.items():
        band_counts[_band_index(credits, width)] += count
    under = sum(count for credits, count in counts.items() if credits < UNDER_CREDITS)
    on_track = sum(count for credits, count in counts.items() if credits >= ON_TRACK_CREDITS)
    return LoadCurve(
        group=group,
        n=n,
        median_credits=round(statistics.median(counts.elements()), 1),
        under_12_pct=_shown_percent(under, n),
        on_track_pct=_shown_percent(on_track, n),
        shares=_band_shares(band_counts, n),
    )


def _counts(sql: str, params: list[str]) -> Counter[float]:
    """How many students attempted each credit count, for one query."""
    counts: Counter[float] = Counter()
    for credits, students in _fetch(sql, params):
        counts[float(credits)] += int(students)
    return counts


def dimension_case(name: str) -> str:
    """SQL naming each student's value of one filter, so counts can be grouped by it.

    The fixed conditions don't overlap, so each student lands on one value; anyone none of them
    match (a value the menus don't list) is "other".
    """
    if name == "program":
        return f"CASE WHEN {_NO_PROGRAM} THEN 'none' ELSE cm.program_of_study_year_1 END"
    whens = " ".join(
        f"WHEN {condition} THEN '{value}'" for value, condition in _CONDITIONS[name].items()
    )
    return f"CASE {whens} ELSE 'other' END"


def _active(filters: CourseLoadFilters) -> dict[str, str]:
    """The filters that are on, by name."""
    return {name: value for name, value in filters.model_dump().items() if value != "all"}


def _where(active: dict[str, str]) -> tuple[str, list[str]]:
    """The extra WHERE conditions for the active filters, and the program parameter if any."""
    conditions, params = [], []
    for name, value in active.items():
        if name != "program":
            conditions.append(_CONDITIONS[name][value])
        elif value == "none":
            conditions.append(_NO_PROGRAM)
        else:
            conditions.append(f"cm.program_of_study_year_1 = {_marker()}")
            params.append(value)
    return "".join(f" AND {condition}" for condition in conditions), params


def _years(cohort: CohortLens) -> list[str]:
    """The cohort years a lens counts."""
    return years_for(cohort)


def get_programs(cohort: CohortLens) -> list[ProgramOption]:
    """Programs with 10 or more students with credits in the cohort, biggest first."""
    years = _years(cohort)
    cohorts = ", ".join([_marker()] * len(years))
    rows = _fetch(_PROGRAMS.format(cohorts=cohorts, min_size=MIN_GROUP_SIZE), years)
    return [ProgramOption(code=str(code), label=program_label(str(code))) for code, _ in rows]


def _filter_text(active: dict[str, str]) -> list[str]:
    """Each active filter as the chart's filter list shows it, e.g. "Race: Hispanic"."""
    texts = []
    for name, value in active.items():
        if name == "program":
            label = "None recorded" if value == "none" else program_label(value)
            texts.append(f"Program: {label}")
        else:
            title, labels = _LABELS[name]
            texts.append(f"{title}: {labels[value]}")
    return texts


def _said(count: int) -> str:
    """A count in words that never shows a number from 1 to 9."""
    return f"fewer than {MIN_GROUP_SIZE}" if 0 < count < MIN_GROUP_SIZE else f"{count:,}"


def _load_said(curve: LoadCurve) -> str | None:
    """A curve's under-12 and on-track shares in words, or None if either is hidden."""
    if curve.under_12_pct is None or curve.on_track_pct is None:
        return None
    return (
        f"{curve.under_12_pct}% attempt under {UNDER_CREDITS} credits in year 1 and "
        f"{curve.on_track_pct}% attempt {ON_TRACK_CREDITS} or more"
    )


def _takeaway(everyone: LoadCurve, selected: LoadCurve | None, hidden: str | None) -> str | None:
    """One sentence on the matching students against everyone, or on everyone alone."""
    if hidden:
        return hidden
    everyone_said = _load_said(everyone)
    if selected is None or selected.n is None:
        return f"Of everyone, {everyone_said}." if everyone_said else None
    selected_said = _load_said(selected)
    if selected_said is None:
        return f"{selected.n:,} students match these filters."
    against = ""
    if everyone.under_12_pct is not None and everyone.on_track_pct is not None:
        against = f" For everyone, it's {everyone.under_12_pct}% and {everyone.on_track_pct}%."
    return f"Of the {selected.n:,} students who match, {selected_said}.{against}"


def _lens_text(cohort: CohortLens) -> str:
    """The cohort lens as the chart's filter list shows it."""
    return lens_label(cohort) if cohort == "all" else f"Cohort {cohort}"


def _meta(
    cohort: CohortLens, active: dict[str, str], width: int, left_out: int, takeaway: str | None
) -> ChartMeta:
    """Title, filters, fields and definitions for one course load response."""
    bands = "one credit at a time" if width == 1 else f"in bands of {width}"
    return ChartMeta(
        title="Course load in year 1",
        description="Share of students at each level of credits attempted in their first year.",
        takeaway=takeaway,
        fields_used=["Number of Credits Attempted Year 1", *(_FIELDS[name] for name in active)],
        filters=[_lens_text(cohort), *_filter_text(active)],
        definitions={
            "Credits attempted": f"Credits attempted at this college in year 1, {bands}.",
            "Share": "The percent of the curve's own students in each band.",
            "On track": (
                f"{ON_TRACK_CREDITS} credits a year finishes a 60-credit associate in 2 years. "
                "The 60 credits is an assumption."
            ),
            "Left out": (
                f"{_said(left_out).capitalize()} students in the cohort with no credits recorded, "
                "or 0 credits, below the dictionary's minimum of 1."
            ),
            "Hidden": (
                f"Groups and bands under {MIN_GROUP_SIZE} students are not shown. When one band is "
                "hidden, the next-smallest is too, so it can't be worked out from the total."
            ),
        },
        source="synthetic",
    )


def _hidden_reason(everyone: LoadCurve, matching: int) -> str | None:
    """Why the matching students can't be shown, or None if they can."""
    if matching < MIN_GROUP_SIZE:
        return f"Fewer than {MIN_GROUP_SIZE} students match these filters."
    left_aside = (everyone.n or 0) - matching
    if 0 < left_aside < MIN_GROUP_SIZE:
        # Everyone's curve minus this one would show the few students the filters leave out.
        return f"These filters leave out fewer than {MIN_GROUP_SIZE} students, so they're hidden."
    return None


def _covered(years: list[str], active: dict[str, str]) -> bool:
    """True if a sibling value is hidden and this selection is its cover (small_counts rule)."""
    from .small_counts import hide_with_cover

    cohorts = ", ".join([_marker()] * len(years))
    for name, value in active.items():
        conditions, params = _where({key: v for key, v in active.items() if key != name})
        sql = _COUNTS_BY_VALUE.format(
            value=dimension_case(name), cohorts=cohorts, filters=conditions
        )
        counts = {str(row[0]): int(row[1]) for row in _fetch(sql, [*years, *params])}
        if value in hide_with_cover(counts):
            return True
    return False


def _selected(
    cohort: CohortLens, active: dict[str, str], everyone: LoadCurve, width: int
) -> tuple[LoadCurve, str | None]:
    """The matching students' curve, or a blank one and the reason it is hidden."""
    matching = "Students who match"
    if lenses.withholds_live_filters(cohort):
        # Checked before counting, so the reason never says anything about the count.
        return _hidden_curve(matching, width), POOL_YEAR_HIDDEN
    years = _years(cohort)
    cohorts = ", ".join([_marker()] * len(years))
    conditions, params = _where(active)
    counts = _counts(_COUNTS.format(cohorts=cohorts, filters=conditions), [*years, *params])
    hidden = _hidden_reason(everyone, sum(counts.values()))
    if hidden is None and _covered(years, active):
        hidden = (
            "Hidden so a smaller group, among this filter's other choices, can't be worked "
            "out by subtraction."
        )
    if hidden:
        return _hidden_curve(matching, width), hidden
    return _curve(matching, counts, width), None


def get_course_load(
    cohort: CohortLens, filters: CourseLoadFilters, granularity: Granularity = "3"
) -> CourseLoadResponse:
    """Year-1 credits curves for everyone in the cohort and for the students who match."""
    width = BAND_WIDTHS[granularity]
    years = _years(cohort)
    cohorts = ", ".join([_marker()] * len(years))
    everyone_counts = _counts(_COUNTS.format(cohorts=cohorts, filters=""), years)
    everyone = _curve("Everyone", everyone_counts, width)

    active = _active(filters)
    selected, hidden = None, None
    if active:
        selected, hidden = _selected(cohort, active, everyone, width)

    left_out = int(_fetch(_LEFT_OUT.format(cohorts=cohorts), years)[0][0])
    bands = band_labels(width)
    return CourseLoadResponse(
        meta=_meta(cohort, active, width, left_out, _takeaway(everyone, selected, hidden)),
        bands=bands,
        on_track_band=bands[_band_index(ON_TRACK_CREDITS, width)],
        everyone=everyone,
        selected=selected,
        hidden_reason=hidden,
    )
