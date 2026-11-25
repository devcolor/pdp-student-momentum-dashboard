"""The student IDs behind the Student Completion Action Board's tiles, as a CSV to download.

One row per student in the selected cohort, flagged by the board's own rules (actions.py): stopped
out after fall, approaching an associate (the college's board only), gateway course barrier, and
outreach priority (in two or more of those; on MVSU's board, in both of its two). With one tile
picked, only the students in it, still with every flag, so it's clear why each is there.
"""

import csv
import io
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.credential_trends import results as credentials
from app.sandbox.executive_view import results as executive
from app.sandbox.executive_view.schemas import CohortLens

from . import actions
from .schemas import School

# Students one export may read: every cohort, with room to spare.
MAX_STUDENTS = 100_000
TIMEOUT_SECONDS = 20.0

# Each flag's column, in the board's order. MVSU's board has no associate tile.
_COLUMNS = {
    "stopped_out": "Stopped_Out_After_Fall",
    "near_15": "Approaching_Associate",
    "gateway": "Gateway_Course_Barrier",
    "priority": "Outreach_Priority",
}


def students_csv(cohort: CohortLens, school: School, tile: str | None) -> str:
    """The CSV text: Student_GUID, Cohort, then each tile's Yes or No for the school's board."""
    names = [name for name in _COLUMNS if not (school == "mvsu" and name == "near_15")]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Student_GUID", "Cohort", *(_COLUMNS[name] for name in names)])

    latest_year = actions._latest_year()
    if latest_year is None:  # no fall and spring to compare, as the board shows nothing
        return out.getvalue()
    years = executive._years_for(cohort)
    sql = actions.STUDENT_FLAGS_SQL.format(
        marker=credentials._placeholders(1),
        key="cm.student_id AS student_id, cm.cohort AS cohort",
        cohorts=credentials._placeholders(len(years)),
    )
    for student, row_cohort, stopped_out, near_15, gateway in _fetch(sql, [latest_year, *years]):
        flags = {"stopped_out": int(stopped_out), "near_15": int(near_15), "gateway": int(gateway)}
        flags["priority"] = _is_priority(flags, school)
        if tile and not flags[tile]:
            continue
        writer.writerow([student, row_cohort, *("Yes" if flags[name] else "No" for name in names)])
    return out.getvalue()


def _is_priority(flags: dict[str, int], school: School) -> int:
    """Outreach priority, as the board counts it: in two or more groups; on MVSU's, in both."""
    if school == "mvsu":
        return int(flags["stopped_out"] + flags["gateway"] == 2)
    return int(flags["stopped_out"] + flags["near_15"] + flags["gateway"] >= 2)


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
