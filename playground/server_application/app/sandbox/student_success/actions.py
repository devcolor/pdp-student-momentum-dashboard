"""Student Completion Action Board: a placeholder showing who might need outreach, as counts only.

Every number is a count of synthetic students, with groups under 10 hidden, and each group column
covered across the pool and its years (executive_view/small_counts.py). There is no
registration, advising or outreach data, so "stopped out" stands in for "not registered" and the
outreach tile only ranks the other three. Near-completers follow the associate momentum page.

MVSU's board drops the associate tile and recommends the next gateway term instead.
"""

from app.sandbox.associate_momentum import results as momentum
from app.sandbox.chat.repo import import_path
from app.sandbox.credential_trends import results as credentials
from app.sandbox.executive_view import cohorts
from app.sandbox.executive_view import results as executive
from app.sandbox.executive_view.schemas import CohortLens, KpiTrend
from app.sandbox.executive_view.small_counts import hide_across_lenses
from app.sandbox.shared import ChartMeta

from . import equity
from .schemas import (
    ActionGroupRow,
    ActionResponse,
    ActionTile,
    EquityDimension,
    GatewayCourseRow,
    School,
)

MIN_GROUP_SIZE = 10
TOP_GATEWAY_COURSES = 6
# Fewer graded enrollments than this make a course's DFW rate too jumpy to rank.
MIN_COURSE_GRADES = 25
# A term needs this many students to count as one the data has really seen.
MIN_TERM_STUDENTS = 100

# The latest academic year with a full fall and spring, so "stopped out" has a spring to miss.
_LATEST_YEAR_SQL = f"""
SELECT t.academic_year
FROM course_enrollment ce
JOIN term t ON t.term_id = ce.term_id
WHERE t.academic_term IN ('FALL', 'SPRING')
GROUP BY t.academic_year
HAVING COUNT(DISTINCT CASE WHEN t.academic_term = 'SPRING' THEN ce.student_id END)
       >= {MIN_TERM_STUDENTS}
ORDER BY t.academic_year DESC
LIMIT 1
"""

_EARNED_SUM = " + ".join(f"COALESCE(cm.{column}, 0)" for column in momentum._EARNED_COLUMNS)

# One row per student with a 0/1 flag for each action. {key} names what each row carries: the
# equity group for the board's counts, or the student and cohort for the ID export.
_FLAGS_CTE = f"""
WITH terms AS (
    SELECT ce.student_id,
           MAX(CASE WHEN t.academic_term = 'FALL' THEN 1 ELSE 0 END) AS took_fall,
           MAX(CASE WHEN t.academic_term = 'SPRING' THEN 1 ELSE 0 END) AS took_spring
    FROM course_enrollment ce
    JOIN term t ON t.term_id = ce.term_id
    WHERE t.academic_year = {{marker}}
    GROUP BY ce.student_id
),
flags AS (
    SELECT {{key}},
           CASE WHEN tr.took_fall = 1 AND tr.took_spring = 0
                 AND COALESCE(cm.first_year_to_associates_at_coho, 0) = 0
                 AND COALESCE(cm.first_year_to_certificate_at_coh, 0) = 0
                THEN 1 ELSE 0 END AS stopped_out,
           CASE WHEN cm.credential_type_sought_year_1 = 'A'
                 AND COALESCE(cm.first_year_to_associates_at_coho, 0) = 0
                 AND ({_EARNED_SUM}) >= {momentum.NEAR_COMPLETER_CREDITS}
                THEN 1 ELSE 0 END AS near_15,
           CASE WHEN cm.credential_type_sought_year_1 = 'A'
                 AND COALESCE(cm.first_year_to_associates_at_coho, 0) = 0
                 AND ({_EARNED_SUM}) >= {momentum.COURSES_SHORT_FROM}
                THEN 1 ELSE 0 END AS near_6,
           CASE WHEN (cm.gateway_math_status = 'R' AND cm.completed_gateway_math_year1 = 'D')
                  OR (cm.gateway_english_status = 'R'
                      AND cm.completed_gateway_english_year1 = 'D')
                THEN 1 ELSE 0 END AS gateway
    FROM cohort_membership cm
    JOIN student s ON s.student_id = cm.student_id
    LEFT JOIN terms tr ON tr.student_id = cm.student_id
    WHERE cm.cohort IN ({{cohorts}})
)
"""

# The flags counted by the equity group, for the board.
_FLAGS_SQL = (
    _FLAGS_CTE
    + """SELECT grp, COUNT(*), SUM(stopped_out), SUM(near_15), SUM(near_6), SUM(gateway),
       SUM(CASE WHEN stopped_out + near_15 + gateway >= 2 THEN 1 ELSE 0 END),
       SUM(CASE WHEN stopped_out + gateway = 2 THEN 1 ELSE 0 END)
FROM flags
GROUP BY grp
"""
)

# The flags per student, for exporting the IDs behind the tiles.
STUDENT_FLAGS_SQL = (
    _FLAGS_CTE
    + """SELECT student_id, cohort, stopped_out, near_15, gateway
FROM flags
ORDER BY cohort, student_id
"""
)

_GATEWAY_GRADES_SQL = """
SELECT ce.math_or_english_gateway, ce.course_name, ce.grade, COUNT(*)
FROM course_enrollment ce
WHERE ce.cohort IN ({cohorts}) AND ce.math_or_english_gateway IN ('M', 'E')
GROUP BY 1, 2, 3
"""

# Tile id, label, what it means, and the suggested next step.
_TILES = [
    (
        "stopped_out",
        "Stopped out after fall",
        "took courses in fall {year} but not that spring, with no credential",
        "Re-enrollment outreach before the next term: check holds, balance and schedule.",
    ),
    (
        "near_15",
        "Approaching an associate",
        "associate-seekers within 15 credits of 60, with no degree yet ({near_6} within 6)",
        "Run a degree audit and build a completion plan for the remaining courses.",
    ),
    (
        "gateway",
        "Gateway course barriers",
        "were required to take gateway math or English and didn't complete it in year 1",
        "Offer co-requisite placement, tutoring or a summer bridge course.",
    ),
    (
        "priority",
        "Outreach priority",
        "students are in two or more of the groups above",
        "Contact these students first. Placeholder: outreach isn't tracked in this data.",
    ),
]
# MVSU is a four-year university: no associate tile, and gateway students get a term to enroll in.
_MVSU_GATEWAY_ACTION = (
    "Recommend enrolling in the gateway course the next semester or the next summer term."
)
_MVSU_PRIORITY_DETAIL = "students are in both groups above"

_COUNT_INDEX = {"stopped_out": 1, "near_15": 2, "near_6": 3, "gateway": 4, "priority": 5}
# Where each school's priority count sits: MVSU's leaves out the associate tile.
_PRIORITY_INDEX = {"ccac": 5, "mvsu": 6}
_COUNT_SIZE = 7


def _shown(count: int) -> int | None:
    """The count, or None when the group is too small to show."""
    return count if count >= MIN_GROUP_SIZE else None


def _latest_year() -> str | None:
    """The latest academic year with a real spring term, or None when there isn't one."""
    rows = credentials._fetch(_LATEST_YEAR_SQL)
    return str(rows[0][0]) if rows else None


def _group_counts(
    dimension: EquityDimension, years: list[str], latest_year: str
) -> dict[str, list[int]]:
    """Per equity group: [students, stopped out, near 15, near 6, gateway, priority, MVSU's]."""
    sql = _FLAGS_SQL.format(
        marker=credentials._placeholders(1),
        key=f"{equity._DIMENSION_COLUMNS[dimension]} AS grp",
        cohorts=credentials._placeholders(len(years)),
    )
    counts: dict[str, list[int]] = {}
    for value, *numbers in credentials._fetch(sql, [latest_year, *years]):
        totals = counts.setdefault(equity._label(dimension, value), [0] * _COUNT_SIZE)
        for index, number in enumerate(numbers):
            totals[index] += int(number or 0)
    return counts


def _dfw_outcomes() -> dict[str, bool]:
    """The shared DFW measure's grade table: grade to whether it is a D, F or withdrawal."""
    import_path(".")
    from measures.calculations import dfw  # type: ignore[import-not-found]

    return dfw.grade_outcomes()


def _gateway_courses(years: list[str]) -> list[GatewayCourseRow]:
    """Gateway courses by DFW rate, highest first, using the shared DFW grade rules."""
    outcomes = _dfw_outcomes()
    sql = _GATEWAY_GRADES_SQL.format(cohorts=credentials._placeholders(len(years)))
    courses: dict[tuple[str, str], list[int]] = {}
    for subject, course, grade, n in credentials._fetch(sql, years):
        key = str(grade).upper() if grade is not None else None
        if key not in outcomes:
            continue
        totals = courses.setdefault((str(subject), str(course)), [0, 0])
        totals[0] += int(outcomes[key]) * int(n)
        totals[1] += int(n)

    rows = [
        GatewayCourseRow(
            course=course,
            subject="Math" if subject == "M" else "English",
            dfw_rate=round(dfw_count / graded * 100, 1),
            n=graded,
        )
        for (subject, course), (dfw_count, graded) in courses.items()
        if graded >= MIN_COURSE_GRADES
    ]
    rows.sort(key=lambda row: -row.dfw_rate)
    return rows[:TOP_GATEWAY_COURSES]


def _count_index(tile_id: str, school: School) -> int:
    """Where a tile's count sits in the per-group totals for this school."""
    return _PRIORITY_INDEX[school] if tile_id == "priority" else _COUNT_INDEX[tile_id]


def _school_tiles(school: School) -> list[tuple[str, str, str, str]]:
    """The tiles a school's board shows: MVSU drops the associate tile and rewords two others."""
    if school == "ccac":
        return _TILES
    tiles = []
    for tile_id, label, meaning, action in _TILES:
        if tile_id == "near_15":
            continue
        if tile_id == "gateway":
            action = _MVSU_GATEWAY_ACTION
        if tile_id == "priority":
            meaning = _MVSU_PRIORITY_DETAIL
        tiles.append((tile_id, label, meaning, action))
    return tiles


def _share(totals: list[int] | None, tile_id: str, school: School = "ccac") -> float | None:
    """A tile's count as a percent of the cohort, or None when it's too small to show."""
    if totals is None or not totals[0]:
        return None
    count = totals[_count_index(tile_id, school)]
    return round(count / totals[0] * 100, 1) if count >= MIN_GROUP_SIZE else None


def _trend(latest: float | None, earlier: float | None, previous_year: str) -> KpiTrend | None:
    """The change in share from the prior cohort, in points: up is red, flat or down is green.

    Every tile counts fewer students as better, so no arrow is ever gray.
    """
    if latest is None or earlier is None:
        return None
    change = round(latest - earlier, 1)
    sign = "+" if change >= 0 else "−"
    label = f"{sign}{abs(change):.1f} pts vs {previous_year}"
    if change == 0:
        return KpiTrend(direction="flat", status="good", label=label)
    rose = change > 0
    return KpiTrend(
        direction="up" if rose else "down", status="bad" if rose else "good", label=label
    )


def _tiles(
    totals: list[int],
    latest_year: str,
    earlier: list[int] | None = None,
    previous_year: str | None = None,
    school: School = "ccac",
) -> list[ActionTile]:
    """The school's action tiles from everyone's counts, each compared with the prior cohort."""
    tiles = []
    for tile_id, label, meaning, action in _school_tiles(school):
        count = totals[_count_index(tile_id, school)]
        shown = _shown(count)
        near_6 = _shown(totals[_COUNT_INDEX["near_6"]])
        detail = meaning.format(
            year=latest_year, near_6=f"{near_6:,}" if near_6 is not None else "fewer than 10"
        )
        tiles.append(
            ActionTile(
                id=tile_id,
                label=label,
                value=shown,
                share=_share(totals, tile_id, school),
                detail=detail,
                action=action,
                trend=_trend(
                    _share(totals, tile_id, school), _share(earlier, tile_id, school), previous_year
                )
                if previous_year
                else None,
            )
        )
    return tiles


def _columns(school: School) -> dict[str, int]:
    """Each column of the group table and where its count sits in the per-group totals."""
    return {
        "n": 0,
        "stopped_out": _COUNT_INDEX["stopped_out"],
        "near_15": _COUNT_INDEX["near_15"],
        "gateway": _COUNT_INDEX["gateway"],
        "priority": _PRIORITY_INDEX[school],
    }


def _hidden_cells(
    by_lens: dict[str, dict[str, list[int]]], cohort: CohortLens, school: School
) -> dict[str, set[str]]:
    """Each column's hidden groups in the lens, every column checked across the lenses alike.

    A column's groups add up to its tile, and its pooled count is the sum of its years'. The n
    column is the equity card's group size, so both cards hide the same groups.
    """
    hidden = {}
    for column, index in _columns(school).items():
        sizes = {
            lens: {label: numbers[index] for label, numbers in counts.items()}
            for lens, counts in by_lens.items()
        }
        hidden[column] = hide_across_lenses(sizes)[cohort]
    return hidden


def _group_rows(
    counts: dict[str, list[int]], hidden: dict[str, set[str]], school: School = "ccac"
) -> list[ActionGroupRow]:
    """Each equity group's count in every action, hidden ones blank, biggest priority first."""
    rows = []
    for label, numbers in counts.items():
        cells = {
            column: None if label in hidden[column] else numbers[index]
            for column, index in _columns(school).items()
        }
        rows.append(ActionGroupRow(group=label, **cells))
    rows.sort(key=lambda row: (row.group == equity.UNKNOWN_LABEL, -(row.priority or 0)))
    return rows


def _takeaway(tiles: list[ActionTile]) -> str | None:
    """One sentence naming the biggest action group."""
    named = [tile for tile in tiles if tile.value is not None and tile.id != "priority"]
    if not named:
        return None
    biggest = max(named, key=lambda tile: tile.value or 0)
    return f"The largest group to act on is {biggest.label.lower()}: {biggest.value:,} students."


def _empty(cohort: CohortLens) -> ActionResponse:
    """The response when the data model has no fall and spring to compare."""
    return ActionResponse(
        meta=ChartMeta(
            title="Student Completion Action Board",
            description="No academic year with a full fall and spring is loaded.",
            fields_used=[],
            filters=executive._cohort_filters(cohort),
            source="synthetic",
        ),
        tiles=[],
        groups=[],
        gateway_courses=[],
    )


def get_actions(
    cohort: CohortLens, dimension: EquityDimension, school: School = "ccac"
) -> ActionResponse:
    """The action tiles, who is in each by one equity group, and the hardest gateway courses."""
    years = executive._years_for(cohort)
    latest_year = _latest_year()
    if latest_year is None:
        return _empty(cohort)

    by_lens = {
        lens: _group_counts(dimension, cohorts.years_for(lens), latest_year)
        for lens in cohorts.lenses_with(cohort)
    }
    counts = by_lens[cohort]
    totals = [sum(numbers[index] for numbers in counts.values()) for index in range(_COUNT_SIZE)]
    previous_year = executive._previous_year(cohort)
    earlier = None
    if previous_year is not None:
        before = _group_counts(dimension, [previous_year], latest_year)
        earlier = [
            sum(numbers[index] for numbers in before.values()) for index in range(_COUNT_SIZE)
        ]
    tiles = _tiles(totals, latest_year, earlier, previous_year, school)
    title = equity.DIMENSION_TITLES[dimension]

    return ActionResponse(
        meta=ChartMeta(
            title="Student Completion Action Board",
            description=(
                "Placeholder: who might need outreach next, and the first step for each group. "
                f"Counts only, split by {title.lower()}."
            ),
            takeaway=_takeaway(tiles),
            fields_used=[
                title,
                "Cohort",
                "Academic term",
                "Credential type sought year 1",
                "Number of credits earned years 1-4",
                "Gateway math and English status",
                "Grade",
            ],
            filters=[
                *executive._cohort_filters(cohort),
                *([f"Arrows: change in share vs {previous_year}"] if previous_year else []),
                "Synthetic data, not real students",
            ],
            definitions=_definitions(latest_year, school),
            source="synthetic",
        ),
        tiles=tiles,
        groups=_group_rows(counts, _hidden_cells(by_lens, cohort, school), school),
        gateway_courses=_gateway_courses(years),
    )


def _definitions(latest_year: str, school: School) -> dict[str, str]:
    """What each tile and mark means, worded for the school's board."""
    definitions = {
        "Arrows": (
            "Each tile's share of its cohort against the prior cohort's, in points. "
            "Fewer students needing action, or no change, is green; more is red. Every "
            "cohort is counted in the same terms, so newer cohorts have had less time."
        ),
        "Stopped out": (
            "A stand-in for 'not registered for next semester': there's no registration "
            f"data, so this is fall {latest_year} students with no spring courses."
        ),
        "Approaching an associate": (
            f"Credits earned in years 1-4 add up to {momentum.NEAR_COMPLETER_CREDITS} or "
            f"more of {momentum.ASSOCIATE_CREDITS}. A credit total is not a degree audit."
        ),
        "Gateway barriers": (
            "Required to take gateway math or English, and not completed in year 1. "
            "Course DFW rates use the shared DFW measure's grade rules, for courses with "
            f"{MIN_COURSE_GRADES} or more graded enrollments."
        ),
        "Outreach priority": (
            "A placeholder ranking: no outreach or advising data is loaded, so contact "
            "isn't tracked."
        ),
        "Hidden": (
            f"Groups under {MIN_GROUP_SIZE} students are not shown. When exactly one in a column "
            "is hidden, the next-smallest is too, so it can't be worked out from the tile, or "
            "from the pooled cohorts minus the other years."
        ),
    }
    if school == "mvsu":
        del definitions["Approaching an associate"]
        definitions["Gateway barriers"] += (
            " The next step is to enroll in the course the next semester or summer term."
        )
    return definitions
