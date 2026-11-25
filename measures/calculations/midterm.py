"""Shared by the midterm measures: one row per course enrollment, with its midterm grade and final grade.

PLANTED: the synthetic midterm grades are generated from the final grades, so any link between a midterm
alert and a D, F or withdrawal is circular by construction. These measures only show the pipeline works.
There is no intervention data either, so recovery says nothing about whether alerts work.
"""
from __future__ import annotations

from .dfw import grade_reasons_sql, grade_values_sql
from ..models import ExclusionReason

# The midterm grades that say how a student is doing. D and L (failing) are alerts. There is no midterm F.
MIDTERM_GRADES = ["A", "B", "C", "D", "L"]
ALERT_GRADES = ["D", "L"]
# A withdrawal before midterm. It says nothing about how the student was doing, so it is outside the measures.
MIDTERM_WITHDRAWAL = "W"

# The enrollment's midterm grade, matched ignoring case and spaces. Blank when it has no midterm row.
MIDTERM = "UPPER(TRIM(mg.midterm_grade))"


def listed(codes: list[str]) -> str:
    """Codes as a SQL list, e.g. ('D', 'L'). The codes are written above, never read from the data."""
    return "(" + ", ".join(f"'{code}'" for code in codes) + ")"


def midterm_rows_sql(in_scope: str, has_answer: str, achieved: str, exclusion_reason: str, where: str = "") -> str:
    """The query for one row per course enrollment with a class, its midterm grade joined, and the student's groups.

    The four expressions decide the answer, as in students.rows_sql. They can use the midterm grade (MIDTERM),
    whether there is a midterm row (mg.student_id), and the final grade: g.is_dfw (blank when it can't be
    classified) and r.reason (why not), from dfw.py's grade lists. where narrows the rows, e.g. to alerts.
    An enrollment matches its midterm row on student, term, course and section; a midterm row is unique on
    those, so the join never repeats an enrollment.
    """
    # Every argument is written in a measure's file, never user input.
    return f"""
WITH grade_outcomes(grade, is_dfw) AS (VALUES {grade_values_sql()}),
grade_reasons(grade, reason) AS (VALUES {grade_reasons_sql()})
SELECT ce.student_id AS student_id,
       ce.cohort AS cohort,
       {in_scope} AS in_scope,
       {has_answer} AS has_answer,
       {achieved} AS achieved,
       {exclusion_reason} AS exclusion_reason,
       s.race AS race,
       s.ethnicity AS ethnicity,
       s.gender AS gender,
       s.first_gen AS first_gen,
       s.student_age AS age_band,
       cm.pell_status_first_year AS pell,
       cm.enrollment_type AS enrollment_type,
       cm.enrollment_intensity_first_term AS enrollment_intensity,
       cm.cohort_term AS cohort_term,
       UPPER(TRIM(c.course_prefix)) || ' ' || UPPER(TRIM(c.course_number)) AS course
FROM course_enrollment ce
JOIN cohort_membership cm ON cm.student_id = ce.student_id AND cm.cohort = ce.cohort
JOIN student s ON s.student_id = ce.student_id
JOIN course c ON c.course_id = ce.course_id
LEFT JOIN midterm_grade mg ON mg.student_id = ce.student_id AND mg.term_id = ce.term_id
     AND mg.course_id = ce.course_id AND mg.section_id = ce.section_id
LEFT JOIN grade_outcomes g ON g.grade = UPPER(TRIM(ce.grade))
LEFT JOIN grade_reasons r ON r.grade = UPPER(TRIM(ce.grade))
{where}"""


# Shared wording for both notes, so the planted label reads the same wherever the note is shown.
PLANTED_NOTE = (
    " PLANTED: the synthetic midterm grades are generated from the final grades, so any link to DFW is circular "
    "by construction and only shows the pipeline works."
)

# Why an enrollment in scope has no midterm answer.
NO_MIDTERM_REASON = (
    f"CASE WHEN mg.student_id IS NULL THEN '{ExclusionReason.NO_MIDTERM_GRADE.value}' "
    f"ELSE '{ExclusionReason.UNLISTED_GRADE.value}' END"
)
