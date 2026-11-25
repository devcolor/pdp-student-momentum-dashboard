"""The institution's uploaded supplemental data, shown back as it was uploaded: one table per file.

Uploaded values sit in student_attribute with a source starting "uploaded:" (see the Workbench's
supplemental upload, app/sandbox/pipeline/supplemental.py), and the data model's built-in sample
with one starting "supplemental:" (all_students_extras.csv), one row per student (and term) and
column. This puts them back into the file's shape: a row per student (and term), a column per
uploaded column, for the selected cohort and the page's filters. Rows are shown however few students
match. Nothing is uploaded on the deployed site, which can't save.
"""

import re
from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.shared import ChartMeta

from .cohorts import lens_label, years_for
from .course_load import _filter_text, _marker, _where
from .schemas import CohortLens, SupplementalFile, SupplementalResponse, SupplementalRow

UPLOADED = "uploaded: "
# A built-in sample: "supplemental: all_students_extras.csv (built-in synthetic sample, ...)".
_BUILT_IN = re.compile(r"^supplemental: (?P<name>[^(]+?)(?: \((?P<note>.*)\))?$")
_SOURCE = re.compile(
    r"^uploaded: (?P<name>.*), (?P<date>\d{4}-\d{2}-\d{2})(?:, (?P<upload>[0-9a-f]{12}))?$"
)
# The most rows one file sends; a bigger file says how many it has.
MAX_ROWS = 500
# Uploaded values one query may read: a full cohort file's students times a handful of columns.
MAX_VALUES = 250_000
TIMEOUT_SECONDS = 20.0

# Every uploaded value for the matching students. attribute_id follows the upload's column order.
_VALUES_SQL = """
SELECT DISTINCT sa.source, sa.student_id, t.academic_year, t.academic_term,
       sa.attribute_key, sa.attribute_value, sa.attribute_id
FROM student_attribute sa
LEFT JOIN term t ON t.term_id = sa.term_id
JOIN cohort_membership cm ON cm.student_id = sa.student_id
JOIN student s ON s.student_id = cm.student_id
WHERE (sa.source LIKE 'uploaded:%%' OR sa.source LIKE 'supplemental:%%')
  AND cm.cohort IN ({cohorts}){filters}
ORDER BY sa.source, sa.student_id, t.academic_year, t.academic_term, sa.attribute_id
"""


def get_supplemental(cohort: CohortLens, active: dict[str, str]) -> SupplementalResponse:
    """Each uploaded file as a table of its matching students' rows."""
    years = years_for(cohort)
    conditions, params = _where(active)
    cohorts = ", ".join([_marker()] * len(years))
    fetched = _fetch(_VALUES_SQL.format(cohorts=cohorts, filters=conditions), [*years, *params])

    by_source: dict[str, list[list]] = {}
    for row in fetched:
        by_source.setdefault(str(row[0]), []).append(list(row[1:]))
    files = [_file(source, rows) for source, rows in sorted(by_source.items())]

    lens = lens_label(cohort)
    return SupplementalResponse(
        meta=ChartMeta(
            title="Supplemental data",
            description="The institution's own uploaded files, a row per student, as uploaded.",
            takeaway=_takeaway(files),
            fields_used=["Student_GUID", "Supplemental uploads (student_attribute)"],
            filters=[lens, *_filter_text(active)],
            definitions={
                "Supplemental data": (
                    "Data the institution uploads in the Workbench where the PDP files fall short, "
                    "shown back as each file was uploaded, for the students who match the filters."
                ),
            },
            source="synthetic",
        ),
        files=files,
    )


def _fetch(sql: str, params: list[str]) -> list[list[Any]]:
    """Run the fixed read-only query with a limit big enough for a whole uploaded file."""
    db, _, _ = query_tool._mcp()
    try:
        result = query_tool.backend().execute(sql, params, MAX_VALUES, TIMEOUT_SECONDS)
    except (db.Unavailable, db.Failed, db.TimedOut) as exc:
        detail = f"The data model couldn't be read: {exc}. Load it from the Sandbox pipeline page."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from None
    if result.truncated:
        detail = f"More than {MAX_VALUES:,} uploaded values match, too many to show here."
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)
    return result.rows


def _file(source: str, values: list[list]) -> SupplementalFile:
    """One uploaded file's rows: a row per student (and term), a column per uploaded column."""
    name, uploaded_on, upload_id = _parse_source(source)
    per_term = any(year is not None for _, year, _, _, _, _ in values)

    rows: dict[tuple, dict[str, str]] = {}
    row_ids: dict[tuple, list[tuple[str, int]]] = {}
    for student, year, term, key, value, attribute_id in values:
        rows.setdefault((student, year, term), {})[key] = value
        row_ids.setdefault((student, year, term), []).append((key, attribute_id))
    columns = _column_order(row_ids.values())
    students = len({student for student, _, _ in rows})

    shown = [
        SupplementalRow(
            student_id=student,
            academic_year=year,
            academic_term=term,
            values={column: row.get(column) for column in columns},
        )
        for (student, year, term), row in list(rows.items())[:MAX_ROWS]
    ]
    return SupplementalFile(
        file=name,
        uploaded_on=uploaded_on,
        upload_id=upload_id,
        per_term=per_term,
        columns=columns,
        students=students,
        total_rows=len(rows),
        rows=shown,
    )


def _parse_source(source: str) -> tuple[str, str | None, str | None]:
    """(file name, upload date, short upload id) from "uploaded: aid.csv, 2026-11-10, 3f2a9c1b7d4e".

    An older upload's source has no id; one that doesn't match at all is shown as it is.
    """
    built_in = _BUILT_IN.match(source)
    if built_in is not None:
        return f"{built_in['name']} (built-in sample)", None, None
    found = _SOURCE.match(source)
    if found is None:
        return source.removeprefix(UPLOADED), None, None
    return found["name"], found["date"], found["upload"]


def _column_order(row_ids: Iterable[list[tuple[str, int]]]) -> list[str]:
    """The uploaded columns in file order.

    Each row's values were stored in column order, but a blank cell stores nothing, so one row can
    put a column early. A column's place is the latest it comes in any row: a full row gives it.
    """
    place: dict[str, int] = {}
    for ids in row_ids:
        for position, (key, _) in enumerate(sorted(ids, key=lambda item: item[1])):
            place[key] = max(place.get(key, 0), position)
    return sorted(place, key=lambda key: (place[key], key))


def _takeaway(files: list[SupplementalFile]) -> str:
    """One sentence on what's uploaded, or how to upload some."""
    if not files:
        return (
            "No supplemental data is loaded. Upload a supplemental file on the Workbench's Upload "
            "page, on a local copy: the deployed site can't save."
        )
    names = ", ".join(file.file for file in files)
    return f"{len(files)} uploaded {'file' if len(files) == 1 else 'files'}: {names}."
