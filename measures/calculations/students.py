"""Shared by the measures that count one answer per student from cohort_membership."""
from __future__ import annotations

from ..models import ExclusionReason


def student_rows_sql(outcome_column: str) -> str:
    """The query for one row per student per cohort, for a measure whose answer is a true, false or blank."""
    # outcome_column is a column name written in a measure's file, never user input.
    return rows_sql(
        has_answer=f"CASE WHEN {outcome_column} IS NULL THEN 0 ELSE 1 END",
        achieved=f"CASE WHEN {outcome_column} IS TRUE THEN 1 ELSE 0 END",
    )


def gateway_rows_sql(completed_column: str, status_column: str) -> str:
    """The query for one row per student per cohort, for a gateway measure.

    Status is R if the student is required to take the course, N if not, and UNKNOWN or blank if nobody knows.
    A student with status N is out of scope: the measure doesn't apply to them.

    Completed is C or D in the file: C means a grade of 1.0 or higher, or a pass, in the first academic year, and
    D means the student did not complete it. Every in-scope student with a C or D is counted. A required student
    who never took the course counts as D. A student with status UNKNOWN or blank, or a required student with a
    blank outcome, can't be classified, so they are left out and counted as excluded.
    """
    # Both arguments are column names written in a measure's file, never user input.
    completed = f"UPPER({completed_column})"
    in_scope = f"CASE WHEN UPPER({status_column}) = 'N' THEN 0 ELSE 1 END"
    return rows_sql(
        has_answer=f"CASE WHEN UPPER({status_column}) = 'N' THEN 0 WHEN {completed} IN ('C', 'D') THEN 1 ELSE 0 END",
        achieved=f"CASE WHEN UPPER({status_column}) = 'N' THEN 0 WHEN {completed} = 'C' THEN 1 ELSE 0 END",
        in_scope=in_scope,
        exclusion_reason=ExclusionReason.UNKNOWN_REQUIREMENT_OR_OUTCOME,
    )


# The student's matrix row for the fall term of their cohort year, if they have one. The matrix has one row
# per student per fall, and a year has one fall term, so this joins at most one row.
FIRST_FALL_JOIN = """
LEFT JOIN (
    SELECT stm.student_id AS student_id,
           t.academic_year AS academic_year,
           stm.retention_fall_to_spring AS retention_fall_to_spring,
           stm.academic_standing AS academic_standing
    FROM student_term_matrix stm
    JOIN term t ON t.term_id = stm.term_id
    WHERE UPPER(t.academic_term) = 'FALL'
) ff ON ff.student_id = cm.student_id AND ff.academic_year = cm.cohort"""


def first_fall_rows_sql(answer_column: str, achieved_value: str, exclusion_reason: ExclusionReason) -> str:
    """The query for one row per student per cohort, for a measure read from the student's first fall matrix row.

    Only fall starters with a matrix row for the fall of their cohort year are in scope: spring, summer and
    winter starters, and fall starters with no fall row, count in n_out_of_scope. An in-scope student whose
    answer is blank is left out with exclusion_reason.
    """
    # Both arguments are written in a measure's file, never user input.
    in_scope = "UPPER(cm.cohort_term) = 'FALL' AND ff.student_id IS NOT NULL"
    return rows_sql(
        has_answer=f"CASE WHEN {in_scope} AND ff.{answer_column} IS NOT NULL THEN 1 ELSE 0 END",
        achieved=f"CASE WHEN {in_scope} AND ff.{answer_column} = '{achieved_value}' THEN 1 ELSE 0 END",
        in_scope=f"CASE WHEN {in_scope} THEN 1 ELSE 0 END",
        exclusion_reason=exclusion_reason,
        joins=FIRST_FALL_JOIN,
    )


def rows_sql(
    has_answer: str,
    achieved: str,
    in_scope: str = "1",
    exclusion_reason: ExclusionReason | str = ExclusionReason.UNKNOWN_OUTCOME,
    joins: str = "",
) -> str:
    """The query for one row per student per cohort: group columns, in_scope, has_answer, achieved and why.

    in_scope is 0 for a student the measure doesn't apply to. Those students are counted apart from the rest.
    achieved is 1 or 0, or a ratio from 0 to 1 for a measure that averages student ratios.
    exclusion_reason says why a row with no answer is left out of the count. It is one ExclusionReason, or a
    query expression (a string) when the reason differs by student. joins is SQL added after the student join,
    for a measure that reads another table.
    """
    reason = f"'{exclusion_reason.value}'" if isinstance(exclusion_reason, ExclusionReason) else exclusion_reason
    return f"""
SELECT cm.student_id AS student_id,
       cm.cohort AS cohort,
       {in_scope} AS in_scope,
       {has_answer} AS has_answer,
       {achieved} AS achieved,
       {reason} AS exclusion_reason,
       s.race AS race,
       s.ethnicity AS ethnicity,
       s.gender AS gender,
       s.first_gen AS first_gen,
       s.student_age AS age_band,
       cm.pell_status_first_year AS pell,
       cm.enrollment_type AS enrollment_type,
       cm.enrollment_intensity_first_term AS enrollment_intensity,
       cm.cohort_term AS cohort_term
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id{joins}
"""
