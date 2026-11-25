"""The executive view's headline tiles and gaps card, read from the published results.

The query builder answers every number here (mcp/pdp_mcp/results.py), so the page, the chat and the
results route all give the same figure for the same cohort and group, and hiding is the one set the
publish step chose. The manifest publishes the pool and each single cohort for the four headline
measures, by the five one-way breakdowns the gaps card compares (measures/manifest.yaml,
single_cohorts). A filter is read from the published results only when it names a published group.
"""

from dataclasses import dataclass
from itertools import combinations

import yaml

from app.sandbox.chat.repo import RepoNotFound
from app.sandbox.results import published as builder
from app.sandbox.results.published import NoMatchingGroups, ResultsUnavailable, page_answer
from app.sandbox.results.schemas import QueryAnswer, QuerySpec, ResultRow

from .cohorts import POOL_YEARS, published_cohort
from .schemas import CohortLens

KPI_MEASURES = ["retention", "persistence", "gateway_math", "gateway_english"]
# The gap finder's default one-way breakdowns (gap_finder/find_gaps.py, DEFAULT_DIMENSIONS).
GAP_DIMENSIONS = ["race", "gender", "pell", "age_band", "enrollment_intensity"]
GAPS_PER_MEASURE = 3
# Any approved breakdown has the everyone row; gender is approved for every lens.
EVERYONE_BREAKDOWN = ["gender"]

# Each page filter that is a published dimension: its dimension, and each value as published.
FILTER_DIMENSIONS: dict[str, tuple[str, dict[str, str]]] = {
    "race": (
        "race",
        {
            "white": "White",
            "hispanic": "Hispanic",
            "black": "Black or African American",
            "asian": "Asian",
            "two_or_more": "Two or More Races",
            "nonresident": "Nonresident alien",
            "american_indian": "American Indian or Alaska Native",
            "pacific_islander": "Native Hawaiian or Other Pacific Islander",
            "unknown": "UNKNOWN",
        },
    ),
    "gender": ("gender", {"female": "F", "male": "M", "x": "X", "unknown": "UNKNOWN"}),
    "age": (
        "age_band",
        {
            "20_and_younger": "20 and younger",
            "over_20_to_24": "> 20-24",
            "over_24": "Older than 24",
            "unknown": "UNKNOWN",
        },
    ),
    "pell": ("pell", {"yes": "Y", "no": "N", "unknown": "UNKNOWN"}),
    "affinity": (
        "affinity",
        {
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
        },
    ),
}


@dataclass(frozen=True)
class Tiles:
    """Each headline measure's published row for one lens and group, and the specs read."""

    rows: dict[str, ResultRow]
    specs: list[QuerySpec]


@dataclass(frozen=True)
class PublishedGap:
    """One group behind everyone else, and each pooled year's students behind for the pool."""

    measure: str
    row: ResultRow
    by_cohort: list[tuple[str, int]] | None


def approved_breakdowns(lens: CohortLens) -> dict[str, set[frozenset[str]]]:
    """Each headline measure's approved breakdowns for the lens's cohort, read once per call.

    A manifest that can't be read or parsed is a server problem, so it is ResultsUnavailable.
    """
    cohort = published_cohort(lens)
    try:
        # Through the module, so a test pointing builder.reader at its own file reaches here.
        results = builder.reader()
        return {
            measure: {frozenset(dims) for dims in results.breakdowns(measure, cohort)}
            for measure in KPI_MEASURES
        }
    except (RepoNotFound, ImportError, OSError, yaml.YAMLError) as error:
        raise ResultsUnavailable(
            f"The published results' manifest can't be read: {error}"
        ) from error
    except (TypeError, ValueError, AttributeError, KeyError) as error:
        raise ResultsUnavailable(
            f"The published results' manifest is malformed: {error}"
        ) from error


def filter_group(
    lens: CohortLens,
    active: dict[str, str],
    approved: dict[str, set[frozenset[str]]] | None = None,
) -> dict[str, str] | None:
    """The published group the page's filters name, e.g. {"pell": "Y"}, or None if there isn't one.

    Every filter must be a published dimension, and the breakdown they make must be approved for
    every headline measure in the lens's cohort, so the tiles all come from the same place.
    approved is approved_breakdowns(lens), when the caller has already read it.
    """
    if not active:
        return None
    group = {}
    for name, value in active.items():
        if name not in FILTER_DIMENSIONS:
            return None
        dimension, values = FILTER_DIMENSIONS[name]
        if value not in values:
            return None
        group[dimension] = values[value]
    if approved is None:
        approved = approved_breakdowns(lens)
    wanted = frozenset(group)
    if all(wanted in approved[measure] for measure in KPI_MEASURES):
        return group
    return None


def kpi_spec(measure: str, lens: CohortLens, group: dict[str, str] | None = None) -> QuerySpec:
    """The spec for one tile: the everyone row with no group, else the group's own row."""
    if not group:
        return QuerySpec(
            measure=measure, cohort=published_cohort(lens), group_by=EVERYONE_BREAKDOWN
        )
    return QuerySpec(
        measure=measure, cohort=published_cohort(lens), group_by=sorted(group), where=group
    )


def _group_row(answer: QueryAnswer, group: dict[str, str]) -> ResultRow | None:
    """The answer's row for exactly this group, or None if it has none."""
    return next((row for row in answer.rows if row.group == group), None)


def published_tiles(lens: CohortLens, group: dict[str, str] | None = None) -> Tiles:
    """Each headline measure's row for the lens: everyone's, or the group's when one is given.

    A group the results have no row for reads as hidden: the deploy's copy can leave it out.
    """
    rows, specs = {}, []
    for measure in KPI_MEASURES:
        spec = kpi_spec(measure, lens, group)
        specs.append(spec)
        try:
            answer = page_answer(spec)
        except NoMatchingGroups:
            rows[measure] = _blank_row(group or {})
            continue
        found = answer.everyone if not group else _group_row(answer, group)
        rows[measure] = found if found is not None else _blank_row(group or {})
    return Tiles(rows=rows, specs=specs)


def published_kpis(lens: CohortLens) -> Tiles:
    """Each headline measure's everyone row for the lens."""
    return published_tiles(lens)


def _blank_row(group: dict[str, str]) -> ResultRow:
    """A hidden row for a group the results don't hold."""
    return ResultRow(
        group=group,
        status="suppressed",
        numerator=None,
        denominator=None,
        metric_rate=None,
        note="Not in the published results.",
    )


def hidden_by_published_subsets(lens: CohortLens, active: dict[str, str]) -> set[str]:
    """The measures whose live tile must be hidden because a broader published group is hidden.

    Each smaller set of the filters is a broader group that the tile's group is part of. When that
    group is published and hidden, live tiles that split it (by the other filters' values) could
    be added back up to it, so the tile is hidden. Every subset is checked, not just one filter
    broader: three filters' tiles can add up to a group two filters broader.
    """
    hidden: set[str] = set()
    names = list(active)
    if len(names) < 2:
        return hidden  # the only broader group is everyone, which is never hidden
    approved = approved_breakdowns(lens)
    for size in range(1, len(names)):
        for kept in combinations(names, size):
            group = filter_group(lens, {name: active[name] for name in kept}, approved)
            if group is None:
                continue
            for measure, row in published_tiles(lens, group).rows.items():
                if row.metric_rate is None:
                    hidden.add(measure)
    return hidden


def gap_specs(lens: CohortLens, measures: list[str]) -> list[QuerySpec]:
    """One spec per measure and one-way breakdown, with gaps."""
    return [
        QuerySpec(
            measure=measure,
            cohort=published_cohort(lens),
            group_by=[dimension],
            include=["rates", "gaps"],
        )
        for measure in measures
        for dimension in GAP_DIMENSIONS
    ]


def _is_behind(row: ResultRow) -> bool:
    """A compared group clearly behind everyone else: not ahead, not unknown, not noise."""
    return (
        row.gap_status == "ok"
        and row.gap_pts is not None
        and row.gap_pts < 0
        and row.likely_noise is False
    )


def published_gaps(
    lens: CohortLens, measures: list[str]
) -> tuple[list[PublishedGap], list[QuerySpec]]:
    """The groups with the most students behind on each measure, and the specs they came from.

    Ranked by the gap finder's rank by students affected, which orders every group published for
    the measure and cohort, so the order within these breakdowns is the same.
    """
    specs = gap_specs(lens, measures)
    answers = [page_answer(spec) for spec in specs]
    gaps = []
    for measure in measures:
        behind = [
            row
            for spec, answer in zip(specs, answers, strict=True)
            if spec.measure == measure
            for row in answer.rows
            if _is_behind(row)
        ]
        behind.sort(key=lambda row: row.rank_by_affected or 0)
        for row in behind[:GAPS_PER_MEASURE]:
            by_cohort = _by_cohort(measure, row) if lens == "all" else None
            gaps.append(PublishedGap(measure=measure, row=row, by_cohort=by_cohort))
    return gaps, specs


def _by_cohort(measure: str, pooled: ResultRow) -> list[tuple[str, int]]:
    """Each pooled year's own students behind for the group; a year not behind counts as 0.

    A year with no compared gap for the group (hidden there) counts as 0 too, as it did when the
    card ran the gap finder live: its bar segment is empty, never a number the year hides.
    """
    [dimension] = pooled.group
    shares = []
    for year in POOL_YEARS:
        spec = QuerySpec(
            measure=measure,
            cohort=year,
            group_by=[dimension],
            where=pooled.group,
            include=["rates", "gaps"],
        )
        try:
            row = _group_row(page_answer(spec), pooled.group)
        except NoMatchingGroups:
            row = None
        affected = row.students_affected if row is not None and row.gap_status == "ok" else None
        shares.append((year, round(max(0.0, -(affected or 0.0)))))
    return shares
