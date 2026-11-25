"""The executive view's cohort lenses: the years each one counts and how the page names it.

Every card on the page reads the lens the same way, so "all" means the same students everywhere.
"all" is the published pool, 2021-22 to 2023-24 (measures/manifest.yaml, cohorts): the query builder
answers it, and 2024-25, which hasn't had every year its measures need, stays out of it.
"""

from .schemas import CohortLens

# The single entering cohorts, oldest first. The manifest publishes each of them (single_cohorts).
SINGLE_YEARS = ["2021-22", "2022-23", "2023-24", "2024-25"]
# The years "all" pools: the manifest's one pooled cohort.
POOL_YEARS = ["2021-22", "2022-23", "2023-24"]
# The pool as the measures label it, e.g. in a QuerySpec.
POOL = " + ".join(POOL_YEARS)
# Retention and persistence need a later year this cohort hasn't fully had yet.
PARTLY_OBSERVED = "2024-25"
# The headline measures that need year 2, which the partly observed cohort hasn't fully had.
NEEDS_YEAR_2 = ("retention", "persistence")


def years_for(lens: CohortLens) -> list[str]:
    """The cohort years a lens counts."""
    return list(POOL_YEARS) if lens == "all" else [lens]


def lenses_with(lens: CohortLens) -> list[str]:
    """The lenses a live count is hidden across: the pool and its years together, else just one.

    The pooled lens is the sum of its years, so a count shown in one can be checked against them.
    """
    if lens == "all" or lens in POOL_YEARS:
        return [*POOL_YEARS, "all"]
    return [lens]


def withholds_live_filters(lens: CohortLens) -> bool:
    """True for a single year inside the pool, where the filters show published groups only.

    A live number for a filter there could be worked out from the pooled lens's minus the other
    years', and a cover wouldn't hold: the filter's sibling values would give it back.
    """
    return lens in POOL_YEARS


def short_of_year_2(measure: str, lens: CohortLens) -> bool:
    """Whether a headline measure needs a year 2 that this single cohort hasn't fully had yet."""
    return measure in NEEDS_YEAR_2 and lens == PARTLY_OBSERVED


def previous_year(lens: CohortLens) -> str | None:
    """The cohort before this one, or None for the pooled lens and the oldest cohort."""
    if lens == "all" or lens == SINGLE_YEARS[0]:
        return None
    return SINGLE_YEARS[SINGLE_YEARS.index(lens) - 1]


def published_cohort(lens: CohortLens) -> str:
    """The lens as the published results name its cohort: the pool's label, or the year."""
    return POOL if lens == "all" else lens


def lens_label(lens: CohortLens) -> str:
    """The lens as a chip names it, e.g. "2023-24 cohort"."""
    if lens == "all":
        return f"Cohorts {POOL_YEARS[0]} to {POOL_YEARS[-1]}, pooled"
    return f"{lens} cohort"


def cohort_chips(lens: CohortLens) -> list[str]:
    """The chips naming which cohorts the numbers count, and whether they're complete yet."""
    if lens == PARTLY_OBSERVED:
        return [lens_label(lens), "Only partly observed so far"]
    return [lens_label(lens)]
