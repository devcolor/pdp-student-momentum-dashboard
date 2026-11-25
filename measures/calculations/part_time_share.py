"""Part-time share: entering students who started part-time. Cohort make-up, not an outcome."""
from __future__ import annotations

from .sql_counts import count_in_sql
from .students import rows_sql
from ..models import Cohort, Counts, Group

NOTE = (
    "Entering students in the cohort whose first-term enrollment intensity is part-time, out of every "
    "entering student. Who entered, not how they did: the denominator is the cohort's entering students."
)

# Every entering student has an answer, so the denominator is the cohort's headcount, as the
# enrollment trends tile counts it. Matched ignoring case: the data model stores Part-Time.
STUDENT_SQL = rows_sql(
    has_answer="1",
    achieved="CASE WHEN UPPER(cm.enrollment_intensity_first_term) = 'PART-TIME' THEN 1 ELSE 0 END",
)


def count(connection, cohorts: list[Cohort], groups: list[Group]) -> dict[tuple[Cohort, Group], Counts]:
    """Count part-time starters among the entering students, for every cohort and group."""
    return count_in_sql(connection, STUDENT_SQL, cohorts, groups)
