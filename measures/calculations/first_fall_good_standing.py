"""Good standing after the first fall: fall starters with a cumulative GPA of 2.0 or more after it."""
from __future__ import annotations

from .sql_counts import count_in_sql
from .students import first_fall_rows_sql
from ..models import Cohort, Counts, ExclusionReason, Group

NOTE = (
    "Fall starters in good academic standing (cumulative GPA 2.0 or more) after their first fall, from the "
    "student matrix row for that fall. A blank standing (no graded credits) is left out. Spring, summer and "
    "winter starters, and fall starters with no row for that fall, are outside the measure. The matrix is "
    "derived from the mock course file."
)

# One row per student per cohort, with whether they have a standing and whether it was good.
STUDENT_SQL = first_fall_rows_sql("academic_standing", "good_standing", ExclusionReason.NO_GRADED_CREDITS)


def count(connection, cohorts: list[Cohort], groups: list[Group]) -> dict[tuple[Cohort, Group], Counts]:
    """Count fall starters in good standing after their first fall in the database for every cohort and group."""
    return count_in_sql(connection, STUDENT_SQL, cohorts, groups)
