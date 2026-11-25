"""Midterm recovery rate: enrollments alerted at midterm (D or L) that did not end in a D, F or withdrawal."""
from __future__ import annotations

from .midterm import ALERT_GRADES, MIDTERM, PLANTED_NOTE, listed, midterm_rows_sql
from .sql_counts import count_in_sql
from ..models import Cohort, Counts, ExclusionReason, Group

NOTE = (
    "Course enrollments of the cohort's students with a D or L (failing) at midterm that did not end in a D, F or "
    "withdrawal, out of those with a final grade, classified as for dfw_rate. There is no intervention data, so "
    "this says nothing about whether alerts work." + PLANTED_NOTE
)

# One row per enrollment alerted at midterm. The final grade decides the answer, as for DFW.
ENROLLMENT_SQL = midterm_rows_sql(
    in_scope="1",
    has_answer="CASE WHEN g.grade IS NULL THEN 0 ELSE 1 END",
    achieved="CASE WHEN g.is_dfw = 0 THEN 1 ELSE 0 END",
    exclusion_reason=f"COALESCE(r.reason, '{ExclusionReason.UNLISTED_GRADE.value}')",
    where=f"WHERE {MIDTERM} IN {listed(ALERT_GRADES)}",
)


def count(connection, cohorts: list[Cohort], groups: list[Group]) -> dict[tuple[Cohort, Group], Counts]:
    """Count alerted enrollments that recovered in the database for every cohort and group."""
    return count_in_sql(connection, ENROLLMENT_SQL, cohorts, groups)
