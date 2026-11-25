"""Course measures by course, and by course x the chosen race and gender, from the query builder.

The rates are the shared measures' (DFW, and the planted midterm alert and recovery), read as the
builder answers them: no SQL and no recomputing here. This file pairs each course's rows, sorts,
cuts to the top courses and counts them. The difference in points is the one sum it does, for
display only, and it is not tested for noise. Publish the results first from the repo root (the
page's intro has the command). The results file is the same one the de-aggregation page reads.
"""

from app.sandbox.deaggregation.results import COHORT, as_rate
from app.sandbox.results.published import NoMatchingGroups, page_answer
from app.sandbox.results.schemas import QuerySpec, ResultRow
from app.sandbox.shared import ChartMeta

from .schemas import (
    Comparison,
    CourseResponse,
    CourseRow,
    GenderChoice,
    MidtermAlertResponse,
    RaceChoice,
    Rate,
    Sort,
)

# Every shown group has at least 10 students, so at least 10 enrollments: the floor drops only
# hidden groups, which read the same as missing ones.
GROUP_MIN_ENROLLMENTS = 10
LIMIT = 15
GENDER_WORDS = {"M": "men", "F": "women"}


def who(race: RaceChoice, gender: GenderChoice) -> str:
    """The chosen group in words, e.g. 'Asian women', 'Asian students', 'Women' or 'Everyone'."""
    if race == "all" and gender == "all":
        return "Everyone"
    if race == "all":
        return GENDER_WORDS[gender].capitalize()
    if gender == "all":
        return f"{race} students"
    return f"{race} {GENDER_WORDS[gender]}"


def chosen(race: RaceChoice, gender: GenderChoice) -> dict[str, str]:
    """The race and gender the group filters on, leaving out a picker set to all."""
    # Gender before race: the order the page's specs have always listed them in.
    where = {}
    if gender != "all":
        where["gender"] = gender
    if race != "all":
        where["race"] = race
    return where


def breakdowns(specs: list[QuerySpec]) -> str:
    """The specs' breakdowns in words, e.g. 'course and course x race'."""
    return " and ".join(" x ".join(spec.group_by) for spec in specs)


def sort_key(sort: Sort):
    """How to order the courses: worst difference, worst group DFW, or most enrollments first."""
    if sort == "group_dfw":
        return lambda row: -(row.group.rate if row.group.rate is not None else -1)
    if sort == "busiest":
        return lambda row: -(row.everyone.n or 0)
    return lambda row: -(row.difference_pts if row.difference_pts is not None else -1000)


def difference_pts(group: Rate, everyone: Rate) -> float | None:
    """The group's rate minus everyone's, in points; blank when either is hidden."""
    if group.rate is None or everyone.rate is None:
        return None
    return round(group.rate - everyone.rate, 1)


def course_specs(
    measure: str, race: RaceChoice, gender: GenderChoice, min_enrollments: int
) -> tuple[QuerySpec, QuerySpec | None]:
    """Everyone by course, and the group by course, or None when the group is everyone."""
    everyone = QuerySpec(
        measure=measure, cohort=COHORT, group_by=["course"], min_denominator=min_enrollments
    )
    where = chosen(race, gender)
    if not where:
        return everyone, None
    group = QuerySpec(
        measure=measure,
        cohort=COHORT,
        group_by=["course", *where],
        where=where,
        min_denominator=GROUP_MIN_ENROLLMENTS,
    )
    return everyone, group


def group_by_course(spec: QuerySpec) -> dict[str, ResultRow]:
    """The group's shown rows by course; none when the group is hidden in every course."""
    try:
        answer = page_answer(spec)
    except NoMatchingGroups:
        # The deploy's trimmed copy drops hidden course rows, so such a group has none at all.
        return {}
    return {row.group["course"]: row for row in answer.rows}


def course_rows(
    measure: str, race: RaceChoice, gender: GenderChoice, min_enrollments: int
) -> tuple[list[CourseRow], list[QuerySpec]]:
    """One row per course with at least min_enrollments, for everyone and for the group."""
    everyone_spec, group_spec = course_specs(measure, race, gender, min_enrollments)
    everyone = page_answer(everyone_spec)
    if group_spec is None:
        by_group = None
        specs = [everyone_spec]
    else:
        by_group = group_by_course(group_spec)
        specs = [everyone_spec, group_spec]

    rows = []
    for course_row in everyone.rows:
        if course_row.status != "ok":
            continue
        course = course_row.group["course"]
        overall = as_rate(course_row)
        if by_group is None:
            # The group is everyone: the same rate twice, and no difference to show.
            group, difference = overall, None
        else:
            group = as_rate(by_group.get(course))
            difference = difference_pts(group, overall)
        rows.append(
            CourseRow(course=course, everyone=overall, group=group, difference_pts=difference)
        )
    return rows, specs


def table_order(sort: Sort, race: RaceChoice, gender: GenderChoice) -> Sort:
    """The sort to use: with everyone as the group there's no difference, so sort by its rate."""
    if sort == "difference" and not chosen(race, gender):
        return "group_dfw"
    return sort


def title(chart: str, race: RaceChoice, gender: GenderChoice) -> str:
    """A chart's title naming the group, against everyone in the course unless it's everyone."""
    if not chosen(race, gender):
        return f"{chart}: Everyone"
    return f"{chart}: {who(race, gender)} against everyone in the course"


def get_courses(
    race: RaceChoice, gender: GenderChoice, min_enrollments: int, sort: Sort
) -> CourseResponse:
    """The courses with at least min_enrollments graded enrollments, worst first for the group."""
    rows, specs = course_rows("dfw_rate", race, gender, min_enrollments)
    hidden = sum(1 for row in rows if row.group.rate is None)
    order = table_order(sort, race, gender)
    rows.sort(key=sort_key(order))
    sorted_by = order.replace("_", " ")
    if order == "group_dfw" and not chosen(race, gender):
        # There's no group, so the page calls this sort "Highest DFW".
        sorted_by = "highest DFW"

    return CourseResponse(
        cohort=COHORT,
        race=race,
        gender=gender,
        group_label=who(race, gender),
        min_enrollments=min_enrollments,
        courses_considered=len(rows),
        courses_with_group_hidden=hidden,
        meta=ChartMeta(
            title=title("DFW rate by course", race, gender),
            description=f"Courses with {min_enrollments}+ graded enrollments, cohorts {COHORT}.",
            takeaway="Counts are course enrollments. A difference is not tested for noise.",
            fields_used=[f"success_measures: dfw_rate by {breakdowns(specs)}"],
            filters=[
                f"Group: {who(race, gender)}",
                f"At least {min_enrollments} enrollments",
                f"Sorted by: {sorted_by}",
            ],
            definitions={
                "DFW rate": "Enrollments ending in a D, F or withdrawal, of those with a grade.",
                "Difference": "The group's DFW rate minus everyone's in the course, in points.",
                "Hidden": "Fewer than 10 students in the group took the course.",
            },
            source="synthetic",
            specs=specs,
        ),
        rows=rows[:LIMIT],
    )


def compare(measure: str, race: RaceChoice, gender: GenderChoice) -> tuple[Comparison, QuerySpec]:
    """One measure across all courses, for the group and for everyone, and the spec it read."""
    where = chosen(race, gender)
    if not where:
        # The group is everyone: read the everyone row beside the race x gender breakdown.
        spec = QuerySpec(measure=measure, cohort=COHORT, group_by=["gender", "race"])
        everyone = as_rate(page_answer(spec).everyone)
        return Comparison(group=everyone, everyone=everyone, difference_pts=None), spec
    spec = QuerySpec(measure=measure, cohort=COHORT, group_by=list(where), where=where)
    answer = page_answer(spec)
    group = as_rate(answer.rows[0] if answer.rows else None)
    everyone = as_rate(answer.everyone)
    difference = difference_pts(group, everyone)
    return Comparison(group=group, everyone=everyone, difference_pts=difference), spec


def get_midterm_alerts(
    race: RaceChoice, gender: GenderChoice, min_enrollments: int
) -> MidtermAlertResponse:
    """The planted midterm alert rate by course, widest difference first, plus recovery."""
    alert, alert_spec = compare("midterm_alert_rate", race, gender)
    recovery, recovery_spec = compare("midterm_recovery_rate", race, gender)
    rows, table_specs = course_rows("midterm_alert_rate", race, gender, min_enrollments)
    hidden = sum(1 for row in rows if row.group.rate is None)
    order = table_order("difference", race, gender)
    rows.sort(key=sort_key(order))

    return MidtermAlertResponse(
        cohort=COHORT,
        race=race,
        gender=gender,
        group_label=who(race, gender),
        min_enrollments=min_enrollments,
        courses_considered=len(rows),
        courses_with_group_hidden=hidden,
        alert=alert,
        recovery=recovery,
        meta=ChartMeta(
            title=title("Midterm alerts by course", race, gender),
            description=(
                f"Courses with {min_enrollments}+ enrollments that have a midterm grade, "
                f"cohorts {COHORT}. A planted stand-in for early alerts."
            ),
            takeaway=(
                "Counts are course enrollments. The midterms are synthetic and planted, so this "
                "shows the pipeline works, not whether alerts help."
            ),
            fields_used=[
                f"success_measures: midterm_alert_rate by {breakdowns(table_specs)}",
                "success_measures: midterm_alert_rate and midterm_recovery_rate by "
                f"{breakdowns([alert_spec])}",
            ],
            filters=[
                f"Group: {who(race, gender)}",
                f"At least {min_enrollments} enrollments with a midterm grade",
                "Sorted by: difference" if order == "difference" else "Sorted by: alert rate",
            ],
            definitions={
                "Midterm alert": (
                    "Enrollments with a midterm D or L (failing), of those with a midterm A, B, "
                    "C, D or L. Midterm withdrawals are left out."
                ),
                "Recovery": (
                    "Alerted enrollments that didn't end in a D, F or withdrawal, of those with "
                    "a final grade."
                ),
                "Difference": (
                    "The group's rate minus everyone's, in points. Not tested for noise."
                ),
                "Hidden": "Fewer than 10 students in the group took the course.",
                "Planted effect": (
                    "The midterm grades are generated from the final grades, so any link "
                    "between an alert and DFW is circular by construction. There is no "
                    "intervention data, so recovery says nothing about whether alerts work. "
                    "Nothing here is a finding about real students."
                ),
            },
            source="synthetic",
            specs=[alert_spec, recovery_spec, *table_specs],
        ),
        rows=rows[:LIMIT],
    )
