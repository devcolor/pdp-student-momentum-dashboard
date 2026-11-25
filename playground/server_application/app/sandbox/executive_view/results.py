"""Headline measures and the largest equity gaps, read from the published results.

The unfiltered tiles and the gaps card come from the query builder (published.py). The graduation
tile, which isn't a shared measure, and tiles for filters that aren't a published group are
counted live from the data model (filtered.py), except on a single year inside the pool.
"""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cache
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.chat.repo import import_path
from app.sandbox.enrollment_trends import results as enrollment_results
from app.sandbox.enrollment_trends.schemas import TermResponse
from app.sandbox.results.schemas import QuerySpec, ResultRow
from app.sandbox.shared import ChartMeta

from . import cohorts, filtered, published
from .course_load import _active
from .schemas import (
    CohortLens,
    CohortShare,
    CourseLoadFilters,
    GapRow,
    GapsResponse,
    KpiTrend,
    TrendKpi,
    TrendKpiResponse,
)

GAPS_PER_MEASURE = published.GAPS_PER_MEASURE
# The older names for the cohort lists, kept for the student success pages and the chat.
_COHORT_YEARS = cohorts.SINGLE_YEARS
_PARTLY_OBSERVED = cohorts.PARTLY_OBSERVED

_KPI_LABELS = {
    "retention": "Retention",
    "persistence": "Persistence elsewhere",
    "gateway_math": "Gateway math",
    "gateway_english": "Gateway English",
}
_KPI_OUTCOMES = {
    "retention": "students returned or earned a credential by the next year",
    "persistence": "students went on at another institution by year 2",
    "gateway_math": "required students completed it in year 1",
    "gateway_english": "required students completed it in year 1",
}

# Persistence is left out: it counts students who went elsewhere, so a low rate isn't a shortfall.
_GAP_MEASURES = {
    "retention": "Retention",
    "gateway_math": "Gateway math",
    "gateway_english": "Gateway English",
}

_GROUP_LABELS = {
    "age_band": {
        "20 and younger": "Age 20 and younger",
        "> 20-24": "Age over 20, up to 24",
        "Older than 24": "Age over 24",
    },
    "enrollment_intensity": {
        "Full-time": "Full-time students",
        "Part-time": "Part-time students",
    },
    "gender": {"F": "Female students", "M": "Male students", "X": "Gender X students"},
    "pell": {"Y": "Pell recipients", "N": "Students without Pell"},
}


# What the graduation tile measures. It isn't a shared measure, so it has no NOTE to read.
_GRADUATION_DEFINITION = (
    "Students who earned a credential at this institution within 150% of the normal time, three "
    "years for an associate. From the institution's own records, which PDP does not carry."
)


# A tooltip has to be readable at a glance. The notes run to four sentences for the gateway
# measures, where the first two say what is counted and the rest is denominator detail.
DEFINITION_LIMIT = 200


@cache
def measure_definitions() -> dict[str, str]:
    """Each tile's label mapped to a short form of the measure's own note, for the page's tooltips.

    Read from the measures rather than written again here, so the page, the published results and
    the chat all say the same thing about what a measure counts.
    """
    definitions = {label: _short(_note_for(name)) for name, label in _KPI_LABELS.items()}
    definitions["Graduation rate"] = _short(_GRADUATION_DEFINITION)
    return definitions


def _note_for(measure: str) -> str:
    """One measure's note, from the module that calculates it."""
    import_path(".")
    from importlib import import_module

    module = import_module(f"measures.calculations.{measure}")
    return getattr(module, "NOTE", "")


def _short(note: str) -> str:
    """The note's first whole sentences, up to DEFINITION_LIMIT.

    Whole sentences, so a tooltip never ends mid-clause. The first is always kept, however long,
    because half a definition is worse than a long one.
    """
    sentences = [part.strip() + "." for part in note.rstrip(".").split(". ") if part.strip()]
    kept = sentences[:1]
    for sentence in sentences[1:]:
        if len(" ".join([*kept, sentence])) > DEFINITION_LIMIT:
            break
        kept.append(sentence)
    return " ".join(kept)


@cache
def _shared() -> tuple[Any, Any, Any]:
    """(gap finder, measure models, measure runner) from the repository's shared code."""
    import_path(".")
    from gap_finder import find_gaps  # type: ignore[import-not-found]
    from measures import models, run_measures  # type: ignore[import-not-found]

    return find_gaps, models, run_measures


@cache
def _shared_compare() -> Any:
    """The shared trend comparison (measures/compare.py)."""
    import_path(".")
    from measures import compare  # type: ignore[import-not-found]

    return compare


def measure_counts(name: str, years: list[str]) -> tuple[int, int] | None:
    """A shared measure's (numerator, denominator) for the cohorts pooled, or None if hidden."""
    _, models, run_measures = _shared()
    with _model_connection() as connection:
        result = run_measures.run_measure(
            models.Measure(name), [models.Cohort.of(*years)], database=connection
        )[0]
    if result.metric_rate is None:
        return None
    return int(result.numerator), int(result.denominator)


@contextmanager
def _model_connection() -> Iterator[Any]:
    """A read-only connection to the data model, turning a model that can't be read into a 503."""
    db, _, _ = query_tool._mcp()
    try:
        with query_tool.backend().connect() as connection:
            yield connection
    except (db.Unavailable, ValueError, sqlite3.Error) as exc:
        detail = f"The data model couldn't be read: {exc}. Load it from the Sandbox pipeline page."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from None


def _years_for(cohort: CohortLens) -> list[str]:
    """The cohort years a lens counts."""
    return cohorts.years_for(cohort)


def _previous_year(cohort: CohortLens) -> str | None:
    """The cohort before this one, or None for the pooled lens and the oldest cohort."""
    return cohorts.previous_year(cohort)


def _cohort_filters(cohort: CohortLens) -> list[str]:
    """The chips naming which cohorts the numbers count."""
    return cohorts.cohort_chips(cohort)


def _percent(rate: float) -> float:
    """A 0-to-1 rate as a percent, to one decimal."""
    return round(rate * 100, 1)


def _trend(
    measure: str, previous: float | None, latest: float | None, previous_year: str
) -> KpiTrend | None:
    """The relative change between two cohorts, read by the shared rules in measures/compare.py."""
    change = _shared_compare().compare_values(measure, previous, latest)
    if change is None:
        return None
    return KpiTrend(
        direction=change.direction, status=change.judgement, label=change.label(previous_year)
    )


def measure_rate(counts: tuple[int, int]) -> float:
    """A measure's (numerator, denominator) as its published metric_rate: rounded to 4 places.

    Tiles that count live compare these, so their arrow is the one publish wrote with compare(),
    even at the edge of the same band.
    """
    return round(counts[0] / counts[1], 4)


def _same_band_filter() -> str:
    """The chip explaining "the same", from the one band every KPI shares."""
    return f"Under {_shared_compare().SAME_WITHIN_PCT:g}% is the same"


def _group_label(group: dict[str, str]) -> str:
    """A plain name for a one-way group; values not listed, such as races, read as they are."""
    [(dimension, value)] = group.items()
    return _GROUP_LABELS.get(dimension, {}).get(value, value)


def _gap_row(gap: published.PublishedGap) -> GapRow:
    """One published gap as the card shows it."""
    row = gap.row
    by_cohort = None
    if gap.by_cohort is not None:
        by_cohort = [
            CohortShare(cohort=cohort, students_behind=behind) for cohort, behind in gap.by_cohort
        ]
    return GapRow(
        measure=_GAP_MEASURES[gap.measure],
        group=_group_label(row.group),
        rate=_percent(row.metric_rate or 0.0),
        gap_pts=round(row.gap_pts or 0.0, 1),
        n=int(row.denominator or 0),
        students_behind=round(abs(row.students_affected or 0.0)),
        by_cohort=by_cohort,
    )


def _largest_gap_takeaway(rows: list[GapRow]) -> str | None:
    """One sentence naming the gap with the most students behind."""
    if not rows:
        return None
    top = max(rows, key=lambda row: row.students_behind)
    return (
        f"Largest gap: {top.group} on {top.measure}, {abs(top.gap_pts)} points below everyone "
        f"else, worth about {top.students_behind:,} students."
    )


# Graduation needs 150% time: 3 years for an associate. Cohorts after this one haven't had it yet.
_LAST_FULLY_GRADUATED = "2022-23"


def _graduation_kpi(
    cohort: CohortLens, active: dict[str, str], hidden_before: set[str] | None = None
) -> TrendKpi | None:
    """The graduation rate tile from the institution's records, or None under 10 students.

    hidden_before is the tiles the page hides on the cohort before; a hidden one gets no arrow.
    """
    graduated, counted = filtered.graduation(_years_for(cohort), active)
    value = filtered.rate(graduated, counted)
    if value is None:
        return None
    previous_year = _previous_year(cohort)
    trend = None
    if previous_year is not None and "graduation" not in (hidden_before or set()):
        before = filtered.rate(*filtered.graduation([previous_year], active))
        trend = _trend("graduation", before, value, previous_year)
    partial = cohort == "all" or cohort > _LAST_FULLY_GRADUATED
    note = " (not all have had 3 years yet)" if partial else ""
    return TrendKpi(
        id="graduation",
        label="Graduation rate",
        unit="percent",
        value=_percent(value),
        detail=(
            f"{graduated:,} of {counted:,} first-time full-time students earned a credential "
            f"within 150% time{note}"
        ),
        trend=trend,
    )


def _published_tile(
    name: str, row: ResultRow, before: ResultRow | None, previous_year: str | None
) -> TrendKpi | None:
    """One measure's tile from its published row, or None when the row is hidden."""
    if row.metric_rate is None or row.numerator is None or row.denominator is None:
        return None
    trend = None
    if previous_year is not None and before is not None:
        trend = _trend(name, before.metric_rate, row.metric_rate, previous_year)
    return TrendKpi(
        id=name,
        label=_KPI_LABELS[name],
        unit="percent",
        value=_percent(row.metric_rate),
        detail=f"{int(row.numerator):,} of {int(row.denominator):,} {_KPI_OUTCOMES[name]}",
        trend=trend,
    )


def _published_items(
    cohort: CohortLens, group: dict[str, str] | None
) -> tuple[list[TrendKpi], list[QuerySpec]]:
    """The headline tiles from the published results, everyone's or one group's, and their specs.

    The trend reads the cohort before's published row for the same group; its specs aren't listed,
    so the specs name only the cohort the tiles show.
    """
    now = published.published_tiles(cohort, group)
    previous_year = _previous_year(cohort)
    before = published.published_tiles(previous_year, group).rows if previous_year else {}
    items = []
    for name, row in now.rows.items():
        tile = _published_tile(name, row, before.get(name), previous_year)
        if tile is not None:
            items.append(tile)
    return items, now.specs


def _live_items(
    cohort: CohortLens, active: dict[str, str], covered: set[str], hidden_before: set[str]
) -> list[TrendKpi]:
    """The headline tiles counted live for the matching students, leaving out covered measures.

    A tile the page hides on the cohort before gets no arrow: the change would give it away.
    """
    previous_year = _previous_year(cohort)
    now = filtered.rates(_years_for(cohort), active)
    before = filtered.rates([previous_year], active) if previous_year else None
    items = []
    for name, (achieved, counted) in now.items():
        value = filtered.rate(achieved, counted)
        if value is None or name in covered:
            continue
        trend = None
        if before is not None and name not in hidden_before:
            trend = _trend(name, filtered.rate(*before[name]), value, previous_year or "")
        items.append(
            TrendKpi(
                id=name,
                label=_KPI_LABELS[name],
                unit="percent",
                value=_percent(value),
                detail=f"{achieved:,} of {counted:,} {_KPI_OUTCOMES[name]}",
                trend=trend,
            )
        )
    return items


_KPI_FIELDS = [
    "Cohort",
    "Retention",
    "Persistence",
    "Gateway math",
    "Gateway English",
    "IPEDS graduation rate status (institution's records, synthetic)",
]


def _year_2_so_far(item: TrendKpi, cohort: CohortLens) -> TrendKpi:
    """A tile whose measure needs year 2, on a cohort short of it: the rate so far, no arrow.

    Against a finished cohort, the share so far would read as a drop. The wording matches
    the student success snapshot's (student_success/results.py, _partial_year_2_tile).
    """
    if not cohorts.short_of_year_2(item.id, cohort):
        return item
    detail = f"{item.detail}; year 2 isn't fully observed yet, so this will likely rise"
    return item.model_copy(update={"trend": None, "detail": detail})


def _withheld_tiles(cohort: CohortLens, active: dict[str, str]) -> set[str]:
    """The tiles a single pooled year withholds for these filters (cohorts.withholds_live_filters).

    Graduation is never published, so it is always withheld there; the other tiles are unless the
    filters name a published group.
    """
    if not cohorts.withholds_live_filters(cohort):
        return set()
    if published.filter_group(cohort, active) is not None:
        return {"graduation"}
    return {*filtered.MEASURES, "graduation"}


def _hidden_tiles(cohort: CohortLens, active: dict[str, str]) -> set[str]:
    """The tiles the filtered page hides for this lens, apart from those under 10 students counted.

    A published group hides what its published rows hide. Otherwise a live tile is hidden when a
    sibling group would be small, or when a broader published group is hidden. Graduation isn't
    published, so the sibling rule always decides it.
    """
    siblings = filtered.hidden_by_siblings(_years_for(cohort), active)
    group = published.filter_group(cohort, active)
    if group is not None:
        rows = published.published_tiles(cohort, group).rows
        hidden = {name for name, row in rows.items() if row.metric_rate is None}
        return hidden | ({"graduation"} & siblings)
    return siblings | published.hidden_by_published_subsets(cohort, active)


def _filtered_kpis(cohort: CohortLens, active: dict[str, str]) -> TrendKpiResponse:
    """The headline measures for only the students who match the page's filters.

    Filters that name a published group read that group's published row, hidden or not. Any other
    filters are counted live, hidden as _hidden_tiles says. An arrow is left off when the tile is
    hidden on the cohort before, or withheld there: on 2024-25 an arrow against 2023-24's
    withheld tile would give its rate back. On a single year inside the pool nothing is counted
    live, not even graduation, so only a published group's tiles show (_withheld_tiles).
    """
    previous_year = _previous_year(cohort)
    group = published.filter_group(cohort, active)
    items: list[TrendKpi] = []
    specs: list[QuerySpec] = []
    if group is not None:
        items, specs = _published_items(cohort, group)
    withheld = cohorts.withholds_live_filters(cohort)
    if not withheld:
        covered = _hidden_tiles(cohort, active)
        hidden_before = set()
        if previous_year is not None:
            hidden_before = _hidden_tiles(previous_year, active)
            hidden_before |= _withheld_tiles(previous_year, active)
        if group is None:
            items = _live_items(cohort, active, covered, hidden_before)
        graduation = _graduation_kpi(cohort, active, hidden_before)
        if graduation is not None and "graduation" not in covered:
            items.append(graduation)
    items = [_year_2_so_far(item, cohort) for item in items]

    chips = _cohort_filters(cohort) + filtered.filter_chips(active)
    if withheld:
        chips.append("Single pooled years: filters show published groups only")
    if previous_year is not None and items:
        chips += [f"Arrows: relative change vs {previous_year}", _same_band_filter()]
    return TrendKpiResponse(
        meta=ChartMeta(
            title="Headline measures",
            description=(
                "The shared success measures for the students who match the filters. A measure "
                "is hidden with fewer than 10 students counted, or when showing it would let a "
                "smaller group be worked out by subtraction."
            ),
            fields_used=_KPI_FIELDS,
            filters=[*chips, "Synthetic data, not real students"],
            definitions=measure_definitions(),
            source="synthetic",
            specs=specs,
        ),
        items=items,
    )


def get_kpis(cohort: CohortLens, filters: CourseLoadFilters | None = None) -> TrendKpiResponse:
    """Each shared measure for one cohort or the pool, with its trend, from published results."""
    active = _active(filters) if filters else {}
    if active:
        return _filtered_kpis(cohort, active)
    items, specs = _published_items(cohort, None)
    previous_year = _previous_year(cohort)

    filters = _cohort_filters(cohort)
    if previous_year is not None:
        filters += [f"Arrows: relative change vs {previous_year}", _same_band_filter()]

    graduation = _graduation_kpi(cohort, {})
    if graduation is not None:
        items.append(graduation)
    items = [_year_2_so_far(item, cohort) for item in items]
    return TrendKpiResponse(
        meta=ChartMeta(
            title="Headline measures",
            description="The shared success measures for all students in the selected cohorts.",
            fields_used=_KPI_FIELDS,
            filters=[*filters, "Synthetic data, not real students"],
            definitions=measure_definitions(),
            source="synthetic",
            specs=specs,
        ),
        items=items,
    )


def get_headcount(filters: CourseLoadFilters | None = None) -> TermResponse:
    """The enrollment trends headcount, with its text reworded for one line per cohort."""
    active = _active(filters) if filters else {}
    if active:
        return filtered.headcount(active)
    headcount = enrollment_results.get_by_term()
    meta = headcount.meta.model_copy(
        update={
            "title": "Headcount by terms since entry",
            "takeaway": (
                "Each line follows one entering cohort, with Term 1 as its first fall. A falling "
                "line means fewer of that cohort are taking courses here."
            ),
        }
    )
    return TermResponse(meta=meta, rows=headcount.rows)


def get_gaps(cohort: CohortLens) -> GapsResponse:
    """The groups furthest behind everyone else in the selected cohorts, from the published gaps."""
    found, specs = published.published_gaps(cohort, list(_GAP_MEASURES))
    rows = [_gap_row(gap) for gap in found]
    return GapsResponse(
        meta=ChartMeta(
            title="Equity gaps",
            description=(
                f"The {GAPS_PER_MEASURE} groups with the most students behind on each measure, "
                "each compared with all other students in the same cohorts. Always all students: "
                "a gap compares groups, so the filters above don't apply."
            ),
            takeaway=_largest_gap_takeaway(rows),
            fields_used=["Race", "Gender", "Pell status", "Age", "First-term intensity"],
            filters=_cohort_filters(cohort),
            definitions={
                # The measure names are headings on this card too, so they are explained here.
                **measure_definitions(),
                "Students behind": (
                    "How many more students in the group would have reached the measure at "
                    "everyone else's rate."
                ),
                "Left out": (
                    "Hidden groups (under 10 students, or hidden so a smaller group can't be "
                    "worked out), unknown groups, groups ahead of everyone else, and gaps likely "
                    "to be noise."
                ),
                "Gateway": (
                    "Only students known to be required to take the course are counted. "
                    "A gap shows a difference between groups, not its cause."
                ),
                "Stacked bars": (
                    f"With the {cohorts.POOL_YEARS[0]} to {cohorts.POOL_YEARS[-1]} cohorts pooled, "
                    "each color is one cohort's own students behind, scaled to fit the pooled "
                    "total."
                ),
            },
            source="synthetic",
            specs=specs,
        ),
        rows=rows,
    )
