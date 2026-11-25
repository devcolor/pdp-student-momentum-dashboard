"""Reads manifest.yaml: the measure, cohort and breakdown combinations approved for publication."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import COURSE_MEASURES, EVERYONE, OPEN_DIMENSIONS, Cohort, Group, GroupBy, GroupDimension, Measure

MANIFEST = Path(__file__).parent / "manifest.yaml"
MAX_DIMENSIONS = 3  # past three, most groups are under 10 and hidden, and a breakdown is hard to read


@dataclass(frozen=True)
class Manifest:
    """The approved combinations, and the file's checksum so a reader can tell which manifest it was."""

    version: int
    cohorts: tuple[Cohort, ...]
    breakdowns: dict[Measure, tuple[GroupBy, ...]]
    sha256: str
    # Single years published beside the cohorts above, and the breakdowns each measure has for them.
    single_cohorts: tuple[Cohort, ...] = ()
    single_breakdowns: dict[Measure, tuple[GroupBy, ...]] = field(default_factory=dict)
    # The single years each measure gets no trend row for (single_cohorts, no_trend).
    no_trend: dict[Measure, frozenset[str]] = field(default_factory=dict)

    def runs(self, measure: Measure) -> list[list[Cohort]]:
        """The cohorts of each run publish.py makes for the measure.

        A measure with single cohorts has one run for all its cohorts, so hiding can check each pool
        against its single years. Any other measure has one run per cohort, as before single cohorts.
        """
        if measure in self.single_breakdowns:
            return [[*self.cohorts, *self.single_cohorts]]
        return [[cohort] for cohort in self.cohorts]

    def approves(self, measure: Measure, cohort: Cohort, group: Group) -> bool:
        """Whether a row for this measure, cohort and group is published. Everyone is, in every cohort it has."""
        if cohort in self.cohorts:
            allowed = self.breakdowns.get(measure)
        elif cohort in self.single_cohorts:
            allowed = self.single_breakdowns.get(measure)
        else:
            allowed = None
        if allowed is None:
            return False
        return group == EVERYONE or GroupBy(frozenset(part.dimension for part in group.parts)) in allowed


def load_manifest(path: Path = MANIFEST) -> Manifest:
    """The manifest at path, checked. Raises ValueError naming the first thing wrong with it."""
    raw = path.read_bytes()
    data = yaml.safe_load(raw) or {}
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError(f"{path.name}: version must be a whole number from 1, not {version!r}")
    cohorts = read_cohorts(data.get("cohorts"))
    breakdowns = read_measures(data.get("measures"))
    single_cohorts, single_breakdowns = read_single_cohorts(data.get("single_cohorts"), cohorts, breakdowns)
    no_trend = read_no_trend((data.get("single_cohorts") or {}).get("no_trend"), single_cohorts, single_breakdowns)
    return Manifest(
        version=version,
        cohorts=cohorts,
        breakdowns=breakdowns,
        sha256=hashlib.sha256(raw).hexdigest(),
        single_cohorts=single_cohorts,
        single_breakdowns=single_breakdowns,
        no_trend=no_trend,
    )


def read_cohorts(entries) -> tuple[Cohort, ...]:
    """Each entry is a list of years counted together. At least one, and no year in two of them."""
    if not entries:
        raise ValueError("manifest.yaml: cohorts needs at least one list of years")
    cohorts = tuple(Cohort.of(*(str(year) for year in years)) for years in entries)
    if len(set(cohorts)) != len(cohorts):
        raise ValueError("manifest.yaml: a cohort is listed twice")
    # Two cohorts that share a year could be set against each other to recover the years they don't share.
    for index, cohort in enumerate(cohorts):
        for other in cohorts[index + 1:]:
            shared = cohort.years & other.years
            if shared:
                raise ValueError(f"manifest.yaml: cohorts {cohort.label} and {other.label} both hold {', '.join(sorted(shared))}")
    return cohorts


def read_single_cohorts(entry, cohorts: tuple[Cohort, ...], breakdowns: dict) -> tuple[tuple[Cohort, ...], dict]:
    """The single_cohorts block: its years, and each measure's breakdowns for them. Missing means none.

    A pool's single years are published together with the pool, so a pool must have every one of its
    years published singly or none: the pool minus some of its years would give the others. Each
    breakdown must already be approved for the measure, because it is run with the pool's.
    """
    if entry is None:
        return (), {}
    if not isinstance(entry, dict) or not entry.get("years") or not entry.get("measures"):
        raise ValueError("manifest.yaml: single_cohorts needs years and measures")
    if not isinstance(entry["years"], list):
        raise ValueError(f"manifest.yaml: single_cohorts years must be a list of years, not {entry['years']!r}")
    years = [str(year) for year in entry["years"]]
    if len(set(years)) != len(years):
        raise ValueError("manifest.yaml: single_cohorts lists a year twice")
    singles = tuple(Cohort.of(year) for year in years)
    for cohort in cohorts:
        if cohort in singles:
            raise ValueError(f"manifest.yaml: {cohort.label} is already a cohort, so it can't be a single cohort too")
        missing = sorted(cohort.years - set(years))
        if missing and len(missing) < len(cohort.years):
            raise ValueError(
                f"manifest.yaml: single_cohorts has some of the years in {cohort.label} but not {', '.join(missing)}: "
                "list every year of a pooled cohort or none"
            )

    single_breakdowns = read_measures(entry["measures"])
    for measure, listed in single_breakdowns.items():
        approved = breakdowns.get(measure)
        if approved is None:
            raise ValueError(f"manifest.yaml: single_cohorts lists {measure.value}, which measures doesn't")
        for group_by in listed:
            if group_by not in approved:
                names = " x ".join(sorted(d.value for d in group_by.dimensions))
                raise ValueError(f"manifest.yaml: single_cohorts breaks {measure.value} down by {names}, which measures doesn't")
        # A course breakdown's groups are the courses taught in the run's years: one run with the single
        # years would add courses to the pooled rows.
        if any(d in OPEN_DIMENSIONS for group_by in approved for d in group_by.dimensions):
            raise ValueError(f"manifest.yaml: {measure.value} has a course breakdown, so it can't have single cohorts")
    return singles, single_breakdowns


def read_no_trend(entry, singles: tuple[Cohort, ...], single_breakdowns: dict) -> dict[Measure, frozenset[str]]:
    """single_cohorts' no_trend: each measure's single years with no trend row from the year before. Missing means none.

    Each measure must have single cohorts, and each year must be one of them.
    """
    if entry is None:
        return {}
    if not isinstance(entry, dict):
        raise ValueError(f"manifest.yaml: single_cohorts no_trend must map measures to years, not {entry!r}")
    years = {label for cohort in singles for label in cohort.years}
    no_trend = {}
    for name, listed in entry.items():
        try:
            measure = Measure(name)
        except ValueError:
            raise ValueError(f"manifest.yaml: no_trend names {name!r}, which is not a measure") from None
        if measure not in single_breakdowns:
            raise ValueError(f"manifest.yaml: no_trend lists {name}, which has no single cohorts")
        if not isinstance(listed, list) or not listed:
            raise ValueError(f"manifest.yaml: no_trend for {name} must be a list of years, not {listed!r}")
        unknown = sorted(str(year) for year in listed if str(year) not in years)
        if unknown:
            raise ValueError(f"manifest.yaml: no_trend for {name} names {', '.join(unknown)}, which isn't a single cohort")
        no_trend[measure] = frozenset(str(year) for year in listed)
    return no_trend


def read_measures(entries) -> dict[Measure, tuple[GroupBy, ...]]:
    """Each measure's breakdowns, every one checked against the dimensions the measures know."""
    if not entries:
        raise ValueError("manifest.yaml: measures needs at least one measure")
    breakdowns = {}
    for name, listed in entries.items():
        try:
            measure = Measure(name)
        except ValueError:
            raise ValueError(f"manifest.yaml: {name!r} is not a measure ({', '.join(m.value for m in Measure)})") from None
        if not listed:
            raise ValueError(f"manifest.yaml: {name} needs at least one breakdown")
        breakdowns[measure] = tuple(read_breakdown(measure, dimensions) for dimensions in listed)
        if len(set(breakdowns[measure])) != len(breakdowns[measure]):
            raise ValueError(f"manifest.yaml: {name} lists a breakdown twice")
    return breakdowns


def read_breakdown(measure: Measure, dimensions) -> GroupBy:
    """One breakdown: one to MAX_DIMENSIONS known dimensions. course is for COURSE_MEASURES only."""
    if not dimensions or len(dimensions) > MAX_DIMENSIONS:
        raise ValueError(f"manifest.yaml: a {measure.value} breakdown needs 1 to {MAX_DIMENSIONS} dimensions, not {dimensions!r}")
    try:
        parsed = [GroupDimension(name) for name in dimensions]
    except ValueError as error:
        raise ValueError(f"manifest.yaml: {measure.value}: {error}") from None
    if measure not in COURSE_MEASURES and any(d in OPEN_DIMENSIONS for d in parsed):
        allowed = ", ".join(sorted(m.value for m in COURSE_MEASURES))
        raise ValueError(f"manifest.yaml: only {allowed} can be broken down by course, not {measure.value}")
    return GroupBy.of(*parsed)
