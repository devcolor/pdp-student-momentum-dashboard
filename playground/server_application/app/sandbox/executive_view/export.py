"""The student IDs behind the Executive view's headline measures, as a CSV to download.

One row per student in the selected cohort who matches the page's filters, with each measure's
answer as the tiles count it: Yes, No, or blank when the student isn't counted (a blank answer, a
student not required to take a gateway course, or not first-time full-time for graduation). With
one measure picked, only that measure's counted students and its column.
"""

import csv
import io
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool

from .cohorts import years_for
from .course_load import _marker, _where
from .schemas import CohortLens

# Students one export may read: every cohort, with room to spare.
MAX_STUDENTS = 100_000
TIMEOUT_SECONDS = 20.0

# Column name for each measure, in the tiles' order.
MEASURE_COLUMNS = {
    "retention": "Retention",
    "persistence": "Persistence_Elsewhere",
    "gateway_math": "Gateway_Math",
    "gateway_english": "Gateway_English",
    "graduation": "Graduation",
}

# Each student's answers, read the way the tiles count them (filtered.py, the shared measures).
_STUDENTS_SQL = """
SELECT DISTINCT cm.student_id, cm.cohort, cm.retention, cm.persistence,
       cm.gateway_math_status, cm.completed_gateway_math_year1,
       cm.gateway_english_status, cm.completed_gateway_english_year1,
       grad.ipeds_grad_rate_status
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
LEFT JOIN (
    SELECT stm.student_id, t.academic_year, stm.ipeds_grad_rate_status
    FROM student_term_matrix stm
    JOIN term t ON t.term_id = stm.term_id
    WHERE UPPER(t.academic_term) = 'FALL' AND stm.ipeds_grad_rate_status IS NOT NULL
) grad ON grad.student_id = cm.student_id AND grad.academic_year = cm.cohort
WHERE cm.cohort IN ({cohorts}){filters}
ORDER BY cm.cohort, cm.student_id
"""


def students_csv(cohort: CohortLens, active: dict[str, str], measure: str | None) -> str:
    """The CSV text: Student_GUID, Cohort, then each measure's answer (or just the one picked)."""
    years = years_for(cohort)
    conditions, params = _where(active)
    cohorts = ", ".join([_marker()] * len(years))
    rows = _fetch(_STUDENTS_SQL.format(cohorts=cohorts, filters=conditions), [*years, *params])

    names = [measure] if measure else list(MEASURE_COLUMNS)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Student_GUID", "Cohort", *(MEASURE_COLUMNS[name] for name in names)])
    for row in rows:
        answers = _answers(row)
        if measure and answers[measure] == "":
            continue  # with one measure picked, only the students it counts
        writer.writerow([row[0], row[1], *(answers[name] for name in names)])
    return out.getvalue()


def _answers(row: list[Any]) -> dict[str, str]:
    """Each measure's answer for one student: "Yes", "No", or "" when not counted."""
    _, _, retention, persistence, math_status, math_done, english_status, english_done, grad = row
    return {
        "retention": _yes_no(retention),
        "persistence": _yes_no(persistence),
        "gateway_math": _gateway(math_status, math_done),
        "gateway_english": _gateway(english_status, english_done),
        "graduation": "" if grad is None else ("Yes" if grad == "completed" else "No"),
    }


def _yes_no(value: Any) -> str:
    """A stored true, false or blank as Yes, No or "". SQLite stores booleans as 1 and 0."""
    if value is None:
        return ""
    return "Yes" if value in (True, 1, "1", "true", "True") else "No"


def _gateway(required: Any, completed: Any) -> str:
    """Gateway as the shared measure counts it: not required is out; C completed, D didn't."""
    if str(required or "").upper() == "N":
        return ""
    done = str(completed or "").upper()
    if done == "C":
        return "Yes"
    return "No" if done == "D" else ""


def _fetch(sql: str, params: list[str]) -> list[list[Any]]:
    """Run the fixed read-only query with room for every student in the pooled cohorts."""
    db, _, _ = query_tool._mcp()
    try:
        result = query_tool.backend().execute(sql, params, MAX_STUDENTS, TIMEOUT_SECONDS)
    except (db.Unavailable, db.Failed, db.TimedOut) as exc:
        detail = f"The data model couldn't be read: {exc}. Load it from the Sandbox pipeline page."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from None
    if result.truncated:
        detail = f"More than {MAX_STUDENTS:,} students match, too many to export at once."
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)
    return result.rows
