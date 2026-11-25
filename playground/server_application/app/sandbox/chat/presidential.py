"""The sentences the model is told about a card clicked on the presidential view.

Every card there is calculated live from the data model, for one entering cohort or the pool, with
a trend line beside it. A click sends the card's label, its value and its trend, never a sentence:
the label is checked against the page's own tiles and the numbers are bounded (schemas.py), and
this module writes every sentence from them.
"""

from functools import cache
from typing import TYPE_CHECKING

from app.sandbox.executive_view import cohorts
from app.sandbox.executive_view import results as executive
from app.sandbox.student_success import results as student_success

from . import context

if TYPE_CHECKING:
    # Only for the annotations: schemas.py imports this module to check a card's label.
    from .schemas import KeywordContext, TrendPoint

# Each card's label mapped to the shared measure behind it, or None for a count. The card called
# Persistence is fall_to_spring_retention; the shared measure persistence is Transfer out.
CARD_MEASURES = {
    label: student_success._MEASURES.get(tile)
    for tile, (label, _) in student_success._TILES.items()
}
COUNT_CARD = student_success._TILES["entering_students"][0]
COMPLETION_CARD = student_success._TILES["completion"][0]
# The published measure whose everyone denominator is the entering students: query_results answers
# the count card with it, and its entering_students_trend is that card's arrow.
ENTERING_MEASURE = "transfer_in_share"

NO_CAUSES = (
    "Nothing in this data records why a value moved, and the data is synthetic: describe how it "
    "moved and do not suggest causes such as programs, policies or the economy."
)


@cache
def allowed_measures() -> frozenset[str]:
    """Every card label a presidential keyword may name, as the page renders it."""
    return frozenset(CARD_MEASURES)


def is_count(label: str | None) -> bool:
    """Whether the card shows a count of students rather than a percent."""
    return label == COUNT_CARD


def published_cohorts(measure: str) -> list[str]:
    """The cohorts query_results holds for one shared measure, or none when it isn't published.

    Read from the manifest, never a fixed list, so a measure published later is picked up.
    """
    from app.sandbox.results.published import reader

    try:
        approved = reader().approved()
    except Exception:  # noqa: BLE001 - nothing is published, which the model should still hear
        return []
    found = approved.get(measure)
    return list(found["cohorts"]) if found else []


def block(keyword: KeywordContext) -> str:
    """What the staff member clicked on the presidential view, as sentences the server wrote."""
    label = keyword.measure
    lines = [
        _looking_at(keyword),
        _card_value(keyword),
        f"On this page, {label} means: {student_success.kpi_definitions()[label]}",
        _which_measure(label),
        _where_the_figures_came_from(label),
        _series(keyword),
        _change(keyword),
        _partly_observed(keyword),
        _same_band(),
        _published_trend(keyword),
        _no_arrow(keyword),
        _completion_check(keyword),
        NO_CAUSES,
    ]
    return " ".join(line for line in lines if line)


def _looking_at(keyword: KeywordContext) -> str:
    """Which card and lens; for Completion pooled, which cohorts the pool really counts."""
    where = context._cohort_phrase(keyword.cohort)
    sentence = f"The staff member is looking at the {keyword.measure} card on the presidential view"
    counted = _completion_pool(keyword)
    if counted:
        window = f"{student_success.COMPLETION_YEARS}-year window"
        return (
            f"{sentence}{where}, counting only {_and_list(counted)}, the pooled cohorts that have "
            f"had the full {window}."
        )
    return f"{sentence}{where}."


def _completion_pool(keyword: KeywordContext) -> list[str]:
    """The pooled cohorts Completion counts when some are short of the window, else none.

    The measure hides a pool with any unfinished cohort, so the card pools only the finished ones.
    """
    if keyword.measure != COMPLETION_CARD or keyword.cohort != "all":
        return []
    finished = [
        point.cohort
        for point in keyword.trend
        if point.cohort in cohorts.POOL_YEARS and not point.partial
    ]
    if len(finished) == len(cohorts.POOL_YEARS):
        return []
    return finished


def _card_value(keyword: KeywordContext) -> str | None:
    """The figure on the card, in the card's own unit, or nothing when none was sent."""
    if is_count(keyword.measure):
        if keyword.n is None:
            return None
        return f"The card shows {keyword.n:,} entering students."
    if keyword.rate is None:
        return None
    shown = f"The card shows {keyword.rate:.1f}%"
    selected = _point(keyword, keyword.cohort)
    if selected is None or not selected.partial:
        return f"{shown}."
    # Says "so far" like the tile, which notes year 2 or the completion window is not over yet.
    if keyword.measure == COMPLETION_CARD:
        window = f"{student_success.COMPLETION_YEARS}-year window"
        return f"{shown}, the share who have completed so far: the {window} isn't over yet."
    return f"{shown} so far: year 2 isn't fully observed yet."


def _which_measure(label: str) -> str:
    """The shared measure behind the card, so the model queries the right one."""
    measure = CARD_MEASURES[label]
    if measure is None:
        return (
            f"This card is a count of entering students, not a shared measure: it is the everyone "
            f"row's denominator of the published {ENTERING_MEASURE}."
        )
    sentence = f"This card is the shared measure {measure}."
    # A card named like another card's measure: say which is which.
    for card, name in CARD_MEASURES.items():
        if name == label.lower() and card != label:
            sentence += (
                f" The shared measure named {name} is a different one: this page calls it {card}."
            )
    return sentence


def _where_the_figures_came_from(label: str) -> str:
    """The card is live; what query_results holds for its measure, if anything.

    Never the executive view's "these are the published results": no card here reads them.
    """
    live = (
        "The card's figures are calculated live from the data model, not read from the published "
        "results, so treat them as given and explain them."
    )
    measure = CARD_MEASURES[label] or ENTERING_MEASURE
    held = published_cohorts(measure)
    if not held:
        return f"{live} {label} is not a published measure, so query_results cannot break it down."
    return (
        f"{live} query_results holds {measure} for {', '.join(held)}; a different cohort there is "
        f"a different number, not a correction, and a refused spec means that cohort is not "
        f"published, which is expected."
    )


def _series(keyword: KeywordContext) -> str:
    """The trend line as the page drew it, oldest first, saying why a point has no value."""
    points = ", ".join(
        f"{point.cohort} {_point_text(keyword.measure, point)}" for point in keyword.trend
    )
    return f"By entering cohort, oldest first: {points}."


def _point_text(label: str | None, point: TrendPoint) -> str:
    """One trend point in words: its value, or why it has none."""
    if point.value is None and point.partial:
        return "not observable yet"
    if point.value is None:
        return f"hidden (fewer than {student_success.MIN_GROUP_SIZE} students)"
    shown = _format(label, point.value)
    return f"{shown} (partly observed)" if point.partial else shown


def _change(keyword: KeywordContext) -> str | None:
    """How the line moved from the first to the last fully observed point, as the page says it.

    The same rule as the page's change label: unfinished cohorts are left out, and fewer than two
    finished points give no change.
    """
    finished = [point for point in keyword.trend if not point.partial and point.value is not None]
    if len(finished) < 2:
        return None
    first, last = finished[0], finished[-1]
    if is_count(keyword.measure):
        difference = round(last.value - first.value)
        amount = f"{abs(difference):,} students"
    else:
        difference = round(last.value - first.value, 1)
        amount = f"{abs(difference):.1f} percentage points"
    sign = "+" if difference >= 0 else "−"
    return (
        f"Across fully observed cohorts, {keyword.measure} went from "
        f"{_format(keyword.measure, first.value)} ({first.cohort}) to "
        f"{_format(keyword.measure, last.value)} ({last.cohort}), {sign}{amount}."
    )


def _partly_observed(keyword: KeywordContext) -> str | None:
    """Why unfinished cohorts' values are low, so a dashed dip is not read as a decline."""
    unfinished = [point.cohort for point in keyword.trend if point.partial]
    if not unfinished:
        return None
    if keyword.measure == COMPLETION_CARD:
        why = (
            f"are still inside the {student_success.COMPLETION_YEARS}-year completion window and "
            f"show the share who have completed so far"
        )
    else:
        why = "have not had every year this measure needs"
    return (
        f"Partly observed cohorts ({_and_list(unfinished)}) {why}, so their values will likely "
        f"rise: a lower value for them is not a decline. Say that rather than explaining the "
        f"change."
    )


def _same_band() -> str:
    """What the card's arrow measures, and the band the page calls the same."""
    same = executive._shared_compare().SAME_WITHIN_PCT
    return (
        f"The card's arrow, when it shows one, is the relative change from the previous cohort, "
        f"and the page treats a relative change under {same:g} percent as the same."
    )


def _published_trend(keyword: KeywordContext) -> str | None:
    """Where the published results hold the card's arrow, for a single cohort that has one.

    The arrow is the change from the previous cohort, which publish wrote with the same rule; the
    trend line's first-to-last change is a different number, so the model is told which is which.
    """
    if keyword.cohort is None or cohorts.previous_year(keyword.cohort) is None:
        return None
    selected = _point(keyword, keyword.cohort)
    if selected is not None and selected.partial:
        return None
    measure = CARD_MEASURES[keyword.measure] or ENTERING_MEASURE
    if keyword.cohort not in published_cohorts(measure):
        return None
    field = "entering_students_trend's label" if is_count(keyword.measure) else "trend_label"
    return (
        f"query_results for {measure}, cohort {keyword.cohort}, with include ['rates', 'trends'] "
        f"gives the card's arrow as {field}: quote it as given. It is not the trend line's "
        f"first-to-last change."
    )


def _completion_check(keyword: KeywordContext) -> str | None:
    """How query_results can, or can't, confirm a Completion card the published results don't hold.

    The pooled card counts only the cohorts that have had the full window, and the published pool
    is not observable yet; a single cohort inside its window shows a count so far.
    """
    if keyword.measure != COMPLETION_CARD:
        return None
    counted = _completion_pool(keyword)
    if counted:
        return (
            f"The published completion pool is not_yet_observable. The card's numerator and "
            f"denominator are the sums of the published single-cohort completion rows for "
            f"{_and_list(counted)}, so query_results can confirm those counts, not a pooled row."
        )
    selected = _point(keyword, keyword.cohort)
    if keyword.cohort != "all" and selected is not None and selected.partial:
        return (
            f"The published completion row for {keyword.cohort} is not_yet_observable, so "
            f"query_results can't confirm this so-far value."
        )
    return None


def _no_arrow(keyword: KeywordContext) -> str | None:
    """Why an unfinished cohort's card has no arrow, so the model doesn't describe one.

    The page leaves the arrow off every partly observed cohort, by the same rule as its trend line.
    """
    if keyword.cohort is None:
        return None
    previous = cohorts.previous_year(keyword.cohort)
    selected = _point(keyword, keyword.cohort)
    if previous is None or selected is None or not selected.partial:
        return None
    return (
        f"The card shows no arrow for {keyword.cohort}: it is partly observed, so a change from "
        f"{previous} would not be like-for-like."
    )


def _point(keyword: KeywordContext, cohort: str | None) -> TrendPoint | None:
    """The trend point for one cohort, or None when the trend has none for it."""
    for point in keyword.trend:
        if point.cohort == cohort:
            return point
    return None


def _format(label: str | None, value: float) -> str:
    """A value in the card's unit: students for a count, a percent otherwise."""
    if is_count(label):
        return f"{value:,.0f} students"
    return f"{value:.1f}%"


def _and_list(items: list[str]) -> str:
    """Items in a sentence: "a", "a and b", or "a, b and c"."""
    if len(items) < 2:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"
