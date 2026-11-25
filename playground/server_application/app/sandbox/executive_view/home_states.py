"""Headcount by home state: where the selected cohort's students lived when they enrolled.

Home state comes from the synthetic home state enrichment, stored in student_attribute. It stands in
for State in the PDP cohort submission file, which the Analysis-Ready File leaves out.
"""

from app.sandbox.shared import ChartMeta

from .cohorts import lens_label, lenses_with, years_for
from .course_load import _fetch, _filter_text, _marker, _where
from .schemas import CohortLens, HomeStateResponse, HomeStateRow
from .small_counts import MIN_GROUP_SIZE, hide_across_lenses

# One row per home state, counting each student once. Students with no home state are "UNKNOWN".
_COUNTS_SQL = """
SELECT COALESCE(hs.attribute_value, 'UNKNOWN') AS state, COUNT(DISTINCT cm.student_id) AS n
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
LEFT JOIN student_attribute hs
  ON hs.student_id = cm.student_id AND hs.attribute_key = 'home_state'
WHERE cm.cohort IN ({cohorts}){filters}
GROUP BY 1
ORDER BY 2 DESC, 1
"""


def _state_counts(cohort: CohortLens, active: dict[str, str]) -> dict[str, int]:
    """Each home state's matching students in one lens."""
    years = years_for(cohort)
    conditions, params = _where(active)
    cohorts = ", ".join([_marker()] * len(years))
    fetched = _fetch(_COUNTS_SQL.format(cohorts=cohorts, filters=conditions), [*years, *params])
    return {str(state): int(n) for state, n in fetched}


def get_home_states(cohort: CohortLens, active: dict[str, str]) -> HomeStateResponse:
    """Count the matching students by home state.

    States under 10 are hidden, and when exactly one is, the next-smallest is too: the states add
    up to the students counted, a total the page shows elsewhere. On the pool and its years, each
    state's pooled count is the sum of its years', so those lenses are hidden together.
    """
    by_lens = {lens: _state_counts(lens, active) for lens in lenses_with(cohort)}
    counts = by_lens[cohort]
    total = sum(counts.values())
    hidden = hide_across_lenses(by_lens)[cohort]
    rows = []
    for state, count in counts.items():
        shown = state not in hidden
        rows.append(
            HomeStateRow(
                state=state,
                n=count if shown else None,
                share=round(count / total * 100, 1) if shown and total else None,
            )
        )

    in_state = next((row for row in rows if row.state == "IL"), None)
    takeaway = None
    if in_state and in_state.n is not None and in_state.share is not None:
        if hidden:
            # A total beside the shown states would give away the hidden ones' sum.
            takeaway = f"{in_state.share}% of these students are from Illinois."
        else:
            others = total - in_state.n
            takeaway = (
                f"{in_state.share}% of these {total:,} students are from Illinois; "
                f"{others:,} came from other states."
            )

    lens = lens_label(cohort)
    return HomeStateResponse(
        meta=ChartMeta(
            title="Headcount by home state",
            description="Where entering students lived when they enrolled.",
            takeaway=takeaway,
            fields_used=[
                "Cohort",
                "Home state (synthetic, stands in for the submission file's State)",
            ],
            filters=[lens, *_filter_text(active)],
            definitions={
                "Home state": (
                    "Synthetic. The real field is State in the PDP cohort submission file, which "
                    "the Analysis-Ready File leaves out. The mock college is placed in Illinois."
                ),
                "Hidden": (
                    f"States under {MIN_GROUP_SIZE} students are not shown. When exactly one is "
                    "hidden, the next-smallest is too, so it can't be worked out from the total, "
                    "or from the pooled cohorts minus the other years."
                ),
            },
            source="synthetic",
        ),
        rows=rows,
    )
