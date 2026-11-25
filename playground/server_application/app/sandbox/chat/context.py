"""The keyword a question came from, and the sentence the model is told about it.

A click on the executive view sends a kind and the names it saw, never a sentence. The server
composes the sentence from values on these lists, so a value rendered from data cannot become a
path from the data into the prompt. Anything not on a list is a 422 and never reaches the model.
"""

from functools import cache
from typing import get_args

from app.sandbox.executive_view.cohorts import PARTLY_OBSERVED, POOL_YEARS
from app.sandbox.executive_view.cohorts import published_cohort as published_cohort
from app.sandbox.executive_view.results import _GAP_MEASURES, _GROUP_LABELS, _KPI_LABELS
from app.sandbox.executive_view.schemas import CohortLens

from .repo import import_path

# PARTLY_OBSERVED is the cohort that has not had every year its measures need: a low rate and a
# downward trend for it are what an unfinished year looks like, not a change worth explaining.
# published_cohort is re-exported, so llm.py names cohorts through this module only.

# These are published and reachable, but their synthetic data was generated from the outcome they
# appear to explain, so an answer has to say the relationship is planted. See AGENTS.md on the
# enrichment generators.
PLANTED_MEASURES = frozenset({"midterm_alert_rate", "midterm_recovery_rate"})
PLANTED_DIMENSIONS = frozenset({"unmet_need_band"})

PLANTED_NOTE = (
    "This measure is planted: the synthetic data it comes from was generated from the outcome it "
    "appears to explain. Say so in your answer, and do not present it as a finding."
)


@cache
def allowed_measures() -> frozenset[str]:
    """Every measure label a keyword may name, as the executive view renders it."""
    return frozenset({*_KPI_LABELS.values(), *_GAP_MEASURES.values()})


@cache
def allowed_groups() -> frozenset[str]:
    """Every group label a keyword may name: the view's own labels, plus the model's own values.

    A gap on a dimension the view has no label for shows the stored value, so both belong here.
    """
    import_path(".")
    from measures.models import ALLOWED_VALUES  # type: ignore[import-not-found]

    labels = {label for dimension in _GROUP_LABELS.values() for label in dimension.values()}
    stored = {value for values in ALLOWED_VALUES.values() for value in values}
    return frozenset(labels | stored)


def allowed_cohorts() -> frozenset[str]:
    """The cohort buttons on the executive view, including the pooled one."""
    return frozenset(get_args(CohortLens))


def published_cohorts() -> list[str]:
    """Every cohort query_results can answer for: the pool and the single years published beside it.

    Not every measure has every cohort: only the headline measures have single years. A spec for a
    cohort a measure doesn't have is refused, so the model is told the list up front rather than
    discovering it and doubting the number on the page.
    """
    from app.sandbox.results.published import reader

    try:
        approved = reader().approved()
    except Exception:  # noqa: BLE001 - nothing is published, which the model should still hear
        return []
    # In the order approved() lists them, pools before single years, without repeats.
    cohorts = (cohort for measure in approved.values() for cohort in measure["cohorts"])
    return list(dict.fromkeys(cohorts))


def is_partly_observed(cohort: str | None) -> bool:
    """Whether the cohort has not had every year its measures need yet."""
    return cohort == PARTLY_OBSERVED


@cache
def planted_group_values() -> frozenset[str]:
    """The stored values of the planted dimensions, so a group keyword on one can be spotted.

    UNKNOWN is left out: every dimension has one, so it says nothing about which dimension a
    group came from, and warning on it would call an unknown race or gender planted.
    """
    import_path(".")
    from measures.models import ALLOWED_VALUES, UNKNOWN, GroupDimension  # type: ignore[import-not-found]

    planted = (d for d in GroupDimension if d.value in PLANTED_DIMENSIONS)
    values = {value for dimension in planted for value in ALLOWED_VALUES[dimension]}
    return frozenset(values - {UNKNOWN})


def planted_note(measure: str | None, group: str | None) -> str | None:
    """The warning to add when a keyword names a planted measure or a planted dimension's value."""
    if measure in PLANTED_MEASURES or (group is not None and group in planted_group_values()):
        return PLANTED_NOTE
    return None


def seed_sentence(kind: str, measure: str | None, group: str | None, cohort: str | None) -> str:
    """One sentence telling the model which number on the page the question came from."""
    where = _cohort_phrase(cohort)
    if kind == "measure":
        return f"The staff member is looking at {measure} on the executive view{where}."
    if kind == "group":
        return (
            f"The staff member is looking at {measure} for {group} on the executive view{where}, "
            f"where that group is behind."
        )
    return f"The staff member is looking at the executive view{where}."


def _cohort_phrase(cohort: str | None) -> str:
    """How to name the cohort in the seed sentence, or nothing when none was sent."""
    if cohort is None:
        return ""
    if cohort == "all":
        return f" for the {POOL_YEARS[0]} to {POOL_YEARS[-1]} cohorts pooled"
    return f" for the {cohort} cohort"
