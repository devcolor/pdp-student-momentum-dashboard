"""Enrollment counts from the normalized data model, made safe to display in a chart."""

from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.shared import ChartMeta

from .schemas import EnteringResponse, EnteringRow, SplitBy, TermResponse, TermRow

MIN_GROUP_SIZE = 10
MAX_ROWS = 200
TIMEOUT_SECONDS = 10.0

# Column names come only from this table, never from the request.
_SPLIT_COLUMNS: dict[SplitBy, str] = {
    "enrollment_type": "enrollment_type",
    "enrollment_intensity": "enrollment_intensity_first_term",
    "pell": "pell_status_first_year",
    "entry_term": "cohort_term",
}
_SPLIT_LABELS: dict[SplitBy, str] = {
    "enrollment_type": "Enrollment type",
    "enrollment_intensity": "First-term intensity",
    "pell": "Pell status, first year",
    "entry_term": "Entry term",
}
_VALUE_LABELS: dict[SplitBy, dict[str, str]] = {
    "enrollment_type": {"UNKNOWN": "Unknown"},
    "enrollment_intensity": {"UNKNOWN": "Unknown"},
    "pell": {"Y": "Pell", "N": "No Pell", "U": "Code U (undefined)", "UNKNOWN": "Unknown"},
    "entry_term": {"FALL": "Fall", "WINTER": "Winter", "SPRING": "Spring", "SUMMER": "Summer"},
}

_BY_TERM_SQL = """
SELECT t.academic_year, t.academic_term, ce.cohort, COUNT(DISTINCT ce.student_id) AS n
FROM course_enrollment ce
JOIN cohort_membership cm ON cm.student_id = ce.student_id AND cm.cohort = ce.cohort
JOIN term t ON t.term_id = ce.term_id
WHERE ce.course_id IS NOT NULL
  AND t.academic_term IN ('FALL', 'SPRING')
  AND t.academic_year <> 'UNKNOWN'
  AND t.academic_year >= ce.cohort
GROUP BY t.sort_order, t.academic_year, t.academic_term, ce.cohort
ORDER BY t.sort_order, ce.cohort
"""


def _fetch(sql: str) -> list[list[Any]]:
    """Run one fixed read-only query, turning any database problem into a clear 503."""
    db, _, _ = query_tool._mcp()
    try:
        return query_tool.backend().execute(sql, None, MAX_ROWS, TIMEOUT_SECONDS).rows
    except (db.Unavailable, db.Failed, db.TimedOut) as exc:
        detail = f"The data model couldn't be read: {exc}. Load it from the Sandbox pipeline page."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from None


def _display_count(count: int) -> int | None:
    """The count, or None when the group is too small to show."""
    return count if count >= MIN_GROUP_SIZE else None


def _percent(part: int, whole: int) -> float:
    """Part as a percent of whole, to one decimal."""
    return round(part / whole * 100, 1)


def _term_label(academic_year: str, academic_term: str) -> str:
    """A short term name: fall of 2021-22 is "Fall 21", its spring is "Spr 22"."""
    if academic_term == "FALL":
        return f"Fall {academic_year[2:4]}"
    return f"Spr {academic_year[5:7]}"


def _biggest_change(
    counts: dict[tuple[str, str], int], totals: dict[str, int], labels: dict[str, str]
) -> str | None:
    """Describe which displayable group's share moved most from the first cohort to the last."""
    cohorts = sorted(totals)
    if len(cohorts) < 2:
        return None
    first, last = cohorts[0], cohorts[-1]
    changes = []
    for value, label in labels.items():
        start, end = counts.get((first, value), 0), counts.get((last, value), 0)
        if start >= MIN_GROUP_SIZE and end >= MIN_GROUP_SIZE:
            start_share, end_share = _percent(start, totals[first]), _percent(end, totals[last])
            changes.append((abs(end_share - start_share), label, start_share, end_share))
    if not changes:
        return None
    _, label, start_share, end_share = max(changes)
    return (
        f"{label} moved the most: {start_share}% of {first} entrants "
        f"to {end_share}% of {last} entrants."
    )


def get_entering(split_by: SplitBy) -> EnteringResponse:
    """Count each cohort's entering students, split by one student group."""
    column = _SPLIT_COLUMNS[split_by]
    fetched = _fetch(
        f"SELECT cohort, COALESCE({column}, 'UNKNOWN') AS value, COUNT(DISTINCT student_id) AS n "
        "FROM cohort_membership GROUP BY 1, 2 ORDER BY 1, 2"
    )
    counts = {(cohort, value): count for cohort, value, count in fetched}

    totals: dict[str, int] = {}
    value_sizes: dict[str, int] = {}
    for (cohort, value), count in counts.items():
        totals[cohort] = totals.get(cohort, 0) + count
        value_sizes[value] = value_sizes.get(value, 0) + count

    # Largest group first, so each cohort's bar stacks in the same order.
    ordered_values = sorted(value_sizes, key=lambda value: (-value_sizes[value], value))
    labels = {value: _VALUE_LABELS[split_by].get(value, value) for value in ordered_values}

    rows = []
    for cohort in sorted(totals):
        for value in ordered_values:
            if (cohort, value) not in counts:
                continue
            count = counts[(cohort, value)]
            shown = _display_count(count)
            rows.append(
                EnteringRow(
                    cohort=cohort,
                    group=labels[value],
                    n=shown,
                    share=None if shown is None else _percent(count, totals[cohort]),
                    cohort_total=totals[cohort],
                )
            )

    return EnteringResponse(
        meta=ChartMeta(
            title=f"Entering students by {_SPLIT_LABELS[split_by].lower()}",
            description="Each group's share of the students in each entering cohort.",
            takeaway=_biggest_change(counts, totals, labels),
            fields_used=["Cohort", _SPLIT_LABELS[split_by]],
            filters=[f"Split by: {_SPLIT_LABELS[split_by]}"],
            definitions={
                "Entering students": "Students in the cohort file for that cohort year.",
                "Share": "The group's students divided by all students in that cohort.",
                "<10": f"Groups under {MIN_GROUP_SIZE} students are not shown.",
            },
            source="synthetic",
        ),
        rows=rows,
    )


def get_by_term() -> TermResponse:
    """Count students taking courses each fall and spring, by the cohort they entered with."""
    fetched = _fetch(_BY_TERM_SQL)

    term_totals: dict[str, int] = {}
    for academic_year, academic_term, _, count in fetched:
        term = _term_label(academic_year, academic_term)
        term_totals[term] = term_totals.get(term, 0) + count

    return TermResponse(
        meta=ChartMeta(
            title="Headcount by term and entering cohort",
            description="Students taking at least one course here each fall and spring.",
            takeaway=(
                "The files follow only the entering cohorts shown, so totals rise as cohorts "
                "accumulate and fall once none are added. This is not institutional growth or "
                "decline; follow one cohort to see how it carries forward."
            ),
            fields_used=["Cohort", "Academic year", "Academic term", "Course prefix and number"],
            filters=["Fall and spring only"],
            definitions={
                "Headcount": "Distinct students with a course record at this institution.",
                "Left out": (
                    "Terms enrolled elsewhere, unknown terms, and terms before the cohort year."
                ),
                "<10": f"Groups under {MIN_GROUP_SIZE} students are not shown.",
            },
            source="synthetic",
        ),
        rows=[
            TermRow(
                term=_term_label(academic_year, academic_term),
                cohort=cohort,
                n=_display_count(count),
                term_total=term_totals[_term_label(academic_year, academic_term)],
            )
            for academic_year, academic_term, cohort, count in fetched
        ],
    )
