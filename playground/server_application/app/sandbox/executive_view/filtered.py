"""Headline measures and headcount for only the students who match the page's filters.

The shared measures split by one group at a time, but the page's filters mix up to seven, plus goal
and program. So with filters on that aren't a published group (published.filter_group), these count
straight from the data model, using the shared measures' rules: a blank answer is left out, and
gateway counts only students required to take it.
"""

from app.sandbox.enrollment_trends import results as enrollment_results
from app.sandbox.enrollment_trends.schemas import TermResponse, TermRow

from .course_load import _fetch, _filter_text, _marker, _where, dimension_case
from .small_counts import MIN_GROUP_SIZE, hide_with_cover

# Each measure's achieved and counted students, as the shared measures' student SQL defines them.
_RATES_SQL = """
SELECT
  SUM(CASE WHEN cm.retention IS TRUE THEN 1 ELSE 0 END),
  SUM(CASE WHEN cm.retention IS NULL THEN 0 ELSE 1 END),
  SUM(CASE WHEN cm.persistence IS TRUE THEN 1 ELSE 0 END),
  SUM(CASE WHEN cm.persistence IS NULL THEN 0 ELSE 1 END),
  SUM(CASE WHEN UPPER(cm.gateway_math_status) = 'N' THEN 0
           WHEN UPPER(cm.completed_gateway_math_year1) = 'C' THEN 1 ELSE 0 END),
  SUM(CASE WHEN UPPER(cm.gateway_math_status) = 'N' THEN 0
           WHEN UPPER(cm.completed_gateway_math_year1) IN ('C', 'D') THEN 1 ELSE 0 END),
  SUM(CASE WHEN UPPER(cm.gateway_english_status) = 'N' THEN 0
           WHEN UPPER(cm.completed_gateway_english_year1) = 'C' THEN 1 ELSE 0 END),
  SUM(CASE WHEN UPPER(cm.gateway_english_status) = 'N' THEN 0
           WHEN UPPER(cm.completed_gateway_english_year1) IN ('C', 'D') THEN 1 ELSE 0 END)
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
WHERE cm.cohort IN ({cohorts}){filters}
"""

# The enrollment trends headcount query, joined to the student so the filters can apply.
_BY_TERM_SQL = """
SELECT t.academic_year, t.academic_term, ce.cohort, COUNT(DISTINCT ce.student_id) AS n
FROM course_enrollment ce
JOIN cohort_membership cm ON cm.student_id = ce.student_id AND cm.cohort = ce.cohort
JOIN student s ON s.student_id = cm.student_id
JOIN term t ON t.term_id = ce.term_id
WHERE ce.course_id IS NOT NULL
  AND t.academic_term IN ('FALL', 'SPRING')
  AND t.academic_year <> 'UNKNOWN'
  AND t.academic_year >= ce.cohort{filters}
GROUP BY t.sort_order, t.academic_year, t.academic_term, ce.cohort
ORDER BY t.sort_order, ce.cohort
"""

# Graduation rate, from the institution's own records (the synthetic student matrix stands in):
# the IPEDS status on each first-time full-time student's first fall. Completed means a credential
# within 150% time: 3 years for an associate or certificate, 6 for a bachelor's.
_GRADUATION_SQL = """
SELECT
  SUM(CASE WHEN stm.ipeds_grad_rate_status = 'completed' THEN 1 ELSE 0 END),
  COUNT(*)
FROM cohort_membership cm
JOIN student s ON s.student_id = cm.student_id
JOIN student_term_matrix stm ON stm.student_id = cm.student_id
JOIN term t ON t.term_id = stm.term_id
WHERE UPPER(t.academic_term) = 'FALL' AND t.academic_year = cm.cohort
  AND stm.ipeds_grad_rate_status IS NOT NULL
  AND cm.cohort IN ({cohorts}){filters}
"""

MEASURES = ["retention", "persistence", "gateway_math", "gateway_english"]


def rates(years: list[str], active: dict[str, str]) -> dict[str, tuple[int, int]]:
    """Each measure's (achieved, counted) students in these cohorts, for the matching students."""
    conditions, params = _where(active)
    cohorts = ", ".join([_marker()] * len(years))
    row = _fetch(_RATES_SQL.format(cohorts=cohorts, filters=conditions), [*years, *params])[0]
    counts = [int(value or 0) for value in row]
    return {name: (counts[2 * i], counts[2 * i + 1]) for i, name in enumerate(MEASURES)}


def graduation(years: list[str], active: dict[str, str]) -> tuple[int, int]:
    """(graduated, counted) first-time full-time students in these cohorts who match the filters."""
    conditions, params = _where(active)
    cohorts = ", ".join([_marker()] * len(years))
    row = _fetch(_GRADUATION_SQL.format(cohorts=cohorts, filters=conditions), [*years, *params])[0]
    return int(row[0] or 0), int(row[1] or 0)


def hidden_by_siblings(years: list[str], active: dict[str, str]) -> set[str]:
    """The measures whose tile must be hidden so a smaller sibling group can't be worked out.

    Each active filter's values, with the other filters held, add up to the tile shown without it:
    Pell yes, no and unknown add up to the unfiltered tile. So each filter is a line, checked per
    measure with the shared rule (small_counts.hide_with_cover).
    """
    hidden: set[str] = set()
    cohorts = ", ".join([_marker()] * len(years))
    for name, value in active.items():
        others = {key: v for key, v in active.items() if key != name}
        conditions, params = _where(others)
        sql = _RATES_SQL.replace("SELECT\n", f"SELECT {dimension_case(name)} AS value,\n", 1)
        sql = sql.format(cohorts=cohorts, filters=conditions) + "GROUP BY 1\n"
        rows = _fetch(sql, [*years, *params])
        for i, measure in enumerate(MEASURES):
            counted = {str(row[0]): int(row[2 + 2 * i] or 0) for row in rows}
            if value in hide_with_cover(counted):
                hidden.add(measure)
        grad_sql = _GRADUATION_SQL.replace(
            "SELECT\n", f"SELECT {dimension_case(name)} AS value,\n", 1
        )
        grad_rows = _fetch(
            grad_sql.format(cohorts=cohorts, filters=conditions) + "GROUP BY 1\n", [*years, *params]
        )
        if value in hide_with_cover({str(row[0]): int(row[2] or 0) for row in grad_rows}):
            hidden.add("graduation")
    return hidden


def rate(achieved: int, counted: int) -> float | None:
    """The rate from 0 to 1, or None when fewer than 10 students are counted."""
    if counted < MIN_GROUP_SIZE:
        return None
    return achieved / counted


def filter_chips(active: dict[str, str]) -> list[str]:
    """Each active filter as a chip, e.g. "Race: Hispanic"."""
    return _filter_text(active)


def headcount(active: dict[str, str]) -> TermResponse:
    """The executive view's headcount, counting only the students who match the filters.

    A term with fewer than 10 matching students is left out, so its total is never shown. In each
    term, the cohorts add up to the term total, so a lone hidden cohort gets a cover.
    """
    conditions, params = _where(active)
    fetched = _fetch(_BY_TERM_SQL.format(filters=conditions), params)
    label = enrollment_results._term_label

    by_term: dict[str, dict[str, int]] = {}
    for academic_year, academic_term, cohort, count in fetched:
        by_term.setdefault(label(academic_year, academic_term), {})[cohort] = int(count)
    kept = {
        term: counts for term, counts in by_term.items() if sum(counts.values()) >= MIN_GROUP_SIZE
    }
    hidden = {term: hide_with_cover(counts) for term, counts in kept.items()}

    base = enrollment_results.get_by_term().meta
    meta = base.model_copy(
        update={
            "title": "Headcount by terms since entry",
            "takeaway": (
                "Each line follows one entering cohort's matching students, with Term 1 as its "
                "first fall. A falling line means fewer of them are taking courses here."
            ),
            "filters": [*base.filters, *filter_chips(active)],
            "definitions": {
                **base.definitions,
                "Hidden": (
                    f"Terms with fewer than {MIN_GROUP_SIZE} matching students are left out. "
                    f"Cohorts under {MIN_GROUP_SIZE} are hidden, and when a term has exactly one, "
                    "its next-smallest cohort is too, so it can't be worked out from the total."
                ),
            },
        }
    )
    rows = [
        TermRow(
            term=term,
            cohort=cohort,
            n=None if cohort in hidden[term] else count,
            term_total=sum(kept[term].values()),
        )
        for term, counts in kept.items()
        for cohort, count in counts.items()
    ]
    return TermResponse(meta=meta, rows=rows)
