"""Fall-to-spring retention: fall starters still enrolled in the spring after their first fall."""
from __future__ import annotations

from .sql_counts import count_in_sql
from .students import first_fall_rows_sql
from ..models import Cohort, Counts, ExclusionReason, Group

NOTE = (
    "Fall starters still enrolled in the spring after their first fall, from the student matrix row for that "
    "fall. Spring, summer and winter starters, and fall starters with no row for that fall, are outside the "
    "measure. The matrix is derived from the mock course file."
)

# One row per student per cohort, with whether they have an answer and whether they were still enrolled.
STUDENT_SQL = first_fall_rows_sql("retention_fall_to_spring", "still_enrolled", ExclusionReason.UNKNOWN_OUTCOME)


def count(connection, cohorts: list[Cohort], groups: list[Group]) -> dict[tuple[Cohort, Group], Counts]:
    """Count fall starters retained to spring in the database for every cohort and group."""
    return count_in_sql(connection, STUDENT_SQL, cohorts, groups)
