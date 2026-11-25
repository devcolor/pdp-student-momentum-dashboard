"""Midterm alert rate: course enrollments with a D or L (failing) at midterm."""
from __future__ import annotations

from .dfw import courses_in
from .midterm import (
    ALERT_GRADES,
    MIDTERM,
    MIDTERM_GRADES,
    MIDTERM_WITHDRAWAL,
    NO_MIDTERM_REASON,
    PLANTED_NOTE,
    listed,
    midterm_rows_sql,
)
from .sql_counts import count_in_sql
from ..models import Cohort, Counts, Group, GroupDimension

NOTE = (
    "Course enrollments of the cohort's students with a D or L (failing) at midterm, out of those with a midterm "
    "grade of A, B, C, D or L. A withdrawal before midterm is outside the measure, and an enrollment with no "
    "midterm grade is left out." + PLANTED_NOTE
)

# Midterm alerts can also be grouped by course, like DFW.
SUPPORTED_OPEN_DIMENSIONS = frozenset({GroupDimension.COURSE})

# One row per course enrollment with a class. The midterm grade decides the answer.
ENROLLMENT_SQL = midterm_rows_sql(
    in_scope=f"CASE WHEN {MIDTERM} = '{MIDTERM_WITHDRAWAL}' THEN 0 ELSE 1 END",
    has_answer=f"CASE WHEN {MIDTERM} IN {listed(MIDTERM_GRADES)} THEN 1 ELSE 0 END",
    achieved=f"CASE WHEN {MIDTERM} IN {listed(ALERT_GRADES)} THEN 1 ELSE 0 END",
    exclusion_reason=NO_MIDTERM_REASON,
)


def open_values(connection, dimension: GroupDimension, cohorts: list[Cohort]) -> list[str]:
    """The courses with an enrollment in the requested cohorts, such as 'ENGL 1302'."""
    if dimension != GroupDimension.COURSE:
        raise ValueError(f"midterm_alert_rate has no values to find for {dimension.value}")
    return courses_in(connection, ENROLLMENT_SQL, cohorts)


def count(connection, cohorts: list[Cohort], groups: list[Group]) -> dict[tuple[Cohort, Group], Counts]:
    """Count enrollments alerted at midterm in the database for every cohort and group."""
    return count_in_sql(connection, ENROLLMENT_SQL, cohorts, groups)
