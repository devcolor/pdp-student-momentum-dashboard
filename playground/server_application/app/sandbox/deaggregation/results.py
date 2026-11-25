"""One race x gender group across every success measure, from the query builder.

Nothing is recomputed or read with SQL here: each measure is one builder answer over the published
success_measures and equity_gaps, and this file only lines the rows up and rounds them
for display. Publish the results from the repo root first (the page's intro has the command).
"""

from app.sandbox.results.published import page_answer
from app.sandbox.results.schemas import QuerySpec, ResultRow
from app.sandbox.shared import ChartMeta

from .schemas import Gender, OutcomeResponse, OutcomeRow, Race, Rate

COHORT = "2021-22 + 2022-23 + 2023-24"

# Gateway courses, then the first-term checks, then the rest of year 1 and coming back.
MEASURES = {
    "gateway_math": ("Gateway math, year 1", "students", False),
    "gateway_english": ("Gateway English, year 1", "students", False),
    "first_fall_good_standing": ("Good standing after first fall", "students", False),
    "fall_to_spring_retention": ("Fall-to-spring retention", "students", False),
    "credit_completion": ("Credit completion, year 1", "students", False),
    "dfw_rate": ("DFW rate", "enrollments", True),
    "retention": ("Retention", "students", False),
    "persistence": ("Persistence", "students", False),
}

# Why the gap finder doesn't test a measure, so the page can say so instead of showing nothing.
NOT_TESTED = {
    "dfw_rate": (
        "Not tested: it counts course enrollments, and one student's enrollments"
        " aren't independent."
    ),
    "credit_completion": "Not tested: it averages each student's ratio, not a yes-or-no outcome.",
}


def measure_spec(measure: str, race: Race) -> QuerySpec:
    """Both genders of one race on one measure, their gaps if tested, and everyone beside them."""
    return QuerySpec(
        measure=measure,
        cohort=COHORT,
        group_by=["gender", "race"],
        where={"race": race},
        include=["rates"] if measure in NOT_TESTED else ["rates", "gaps"],
    )


def as_rate(row: ResultRow | None) -> Rate:
    """A published row's rate as a percentage. Missing or hidden rows stay blank."""
    if row is None or row.metric_rate is None:
        return Rate(rate=None, n=None)
    return Rate(rate=round(row.metric_rate * 100, 1), n=row.denominator)


def get_outcomes(race: Race, gender: Gender) -> OutcomeResponse:
    """Every measure for one race x gender group, with its gap where the gap finder tests it."""
    other = "F" if gender == "M" else "M"
    specs = []
    rows = []
    for measure, (label, counts, lower_is_better) in MEASURES.items():
        spec = measure_spec(measure, race)
        answer = page_answer(spec)
        specs.append(spec)
        by_gender = {row.group["gender"]: row for row in answer.rows}
        group = by_gender.get(gender)
        # The gap finder compares only shown groups; the rank is among this breakdown's groups.
        gap = group if group is not None and group.gap_status == "ok" else None
        rows.append(
            OutcomeRow(
                measure=measure,
                label=label,
                counts=counts,
                lower_is_better=lower_is_better,
                group=as_rate(group),
                other_gender=as_rate(by_gender.get(other)),
                everyone=as_rate(answer.everyone),
                gap_pts=gap.gap_pts if gap else None,
                ci_low=gap.ci_low if gap else None,
                ci_high=gap.ci_high if gap else None,
                likely_noise=gap.likely_noise if gap else None,
                rank=gap.rank_in_breakdown if gap else None,
                ranked_of=gap.ranked_of if gap else None,
                not_tested=NOT_TESTED.get(measure),
            )
        )

    gender_label = "men" if gender == "M" else "women"
    return OutcomeResponse(
        cohort=COHORT,
        race=race,
        gender=gender,
        meta=ChartMeta(
            title=f"{race} {gender_label}, measure by measure",
            description=f"Cohorts {COHORT} pooled, from the shared measures and the gap finder.",
            takeaway="A gap shows a difference between groups, not its cause.",
            fields_used=["success_measures", "equity_gaps"],
            filters=[f"Race: {race}", f"Gender: {gender_label}", f"Cohorts: {COHORT}"],
            definitions={
                "Gap": "The group's rate minus everyone else's, in percentage points.",
                "Rank": "Among race x gender groups, by students affected. 1 is the most behind.",
                "Likely noise": "The corrected q-value is 0.05 or more.",
                "Hidden": "Fewer than 10 students, so the numbers aren't shown.",
            },
            source="synthetic",
            specs=specs,
        ),
        rows=rows,
    )
