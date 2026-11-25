"""Completion: students who earned an associate or a certificate here within three years of entering."""
from __future__ import annotations

from .sql_counts import count_in_sql
from .students import rows_sql
from ..models import Cohort, Counts, Group

COMPLETION_YEARS = 3
# The last academic year the data can see is still under way, so it doesn't count as a full year.
IN_PROGRESS_YEARS = 1

NOTE = (
    f"Students in the cohort who earned an associate or a certificate at this institution within "
    f"{COMPLETION_YEARS} years, counted once if they earned both. A cohort the data hasn't seen for "
    f"{COMPLETION_YEARS} full years has no answer yet."
)

# A student has an answer once the data has seen the full window for their cohort.
_OBSERVED = f"cm.credit_years_observed - {IN_PROGRESS_YEARS} >= {COMPLETION_YEARS}"
_EARNED = (
    f"cm.first_year_to_associates_at_coho BETWEEN 1 AND {COMPLETION_YEARS} "
    f"OR cm.first_year_to_certificate_at_coh BETWEEN 1 AND {COMPLETION_YEARS}"
)

# One row per student per cohort, with whether the window is observed and whether they completed.
STUDENT_SQL = rows_sql(
    has_answer=f"CASE WHEN {_OBSERVED} THEN 1 ELSE 0 END",
    achieved=f"CASE WHEN {_OBSERVED} AND ({_EARNED}) THEN 1 ELSE 0 END",
)


def count(connection, cohorts: list[Cohort], groups: list[Group]) -> dict[tuple[Cohort, Group], Counts]:
    """Count students who completed within the window, for every cohort and group."""
    return count_in_sql(connection, STUDENT_SQL, cohorts, groups)
