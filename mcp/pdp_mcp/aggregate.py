"""The rules an aggregate query result must pass before anyone sees it.

Aggregate mode answers read-only SQL, so the statement check in query.py and the read-only
database in db.py are not enough on their own: a grouped query can still return a group of one
student, and a student id can still arrive under a column named something else. These rules run
after the query and before the result leaves the server.

Three of them, in the order they are applied:

1. No row-level identifier column. A result that selects student_id, enrollment_id or
   attribute_id is refused outright rather than filtered, because the caller asked the wrong
   question.
2. A count column named `n`, the number of distinct students in each row's group. Without it
   there is nothing to judge a group's size by, so the result is refused.
3. Groups smaller than MIN_GROUP_SIZE are dropped, and the result says how many were dropped.
   Then the kept values are checked against the student table, which catches a student id that
   column names alone would miss (`SELECT student_id AS region ...`).

The same rules back the Playground's run_aggregate_query tool. They live here so the server and
the Playground share one definition rather than two that can drift.

What these rules do NOT do:

- They take `n` on trust. Nothing here checks that it is really a count of distinct students in
  its row's group, or that the query groups at all, so `SELECT race, 999 AS n FROM student WHERE
  race = '<a small race>'` passes all three and returns a row per student. These rules bound a
  client asking in good faith; closing the gap means the server computing the counts itself
  instead of reading one out of the result.
- No complementary suppression. A breakdown where exactly one group is dropped can still be worked
  out by subtraction from a total the caller also asked for. The shared measures hide a second
  group to cover that (run_measures.py); this tool answers SQL directly, so it never sees the
  breakdown as a set of lines and cannot do the same. On this one point a caller reaching the
  measures is better protected than one reaching this tool.
"""

from .query import QueryRejected

__all__ = ["COUNT_COLUMN", "MAX_ROWS", "MIN_GROUP_SIZE", "ROW_ID_COLUMNS",
           "check_result_columns", "keep_large_groups", "holds_student_ids"]

MIN_GROUP_SIZE = 10
COUNT_COLUMN = "n"
MAX_ROWS = 200
# Each identifies one student, enrollment, attribute, matrix or midterm row, so no aggregate
# result needs one.
ROW_ID_COLUMNS = frozenset(
    {"student_id", "enrollment_id", "attribute_id", "matrix_id", "midterm_id"}
)


def check_result_columns(names) -> int:
    """The index of the count column, or raise QueryRejected if the columns aren't aggregate."""
    lowered = [str(name).lower() for name in names]
    identifiers = sorted(ROW_ID_COLUMNS.intersection(lowered))
    if identifiers:
        raise QueryRejected(f"results can't include row-level identifiers "
                            f"({', '.join(identifiers)}). Group by other columns and count students instead")
    if COUNT_COLUMN not in lowered:
        raise QueryRejected(f"the result needs a column named {COUNT_COLUMN}: the number of distinct students "
                            f"in each group, such as COUNT(DISTINCT student_id) AS {COUNT_COLUMN}")
    return lowered.index(COUNT_COLUMN)


def keep_large_groups(rows, count_index: int) -> list:
    """The rows whose group holds at least MIN_GROUP_SIZE students. The rest are dropped."""
    return [row for row in rows if _group_size(row[count_index]) >= MIN_GROUP_SIZE]


def holds_student_ids(backend, rows, timeout_seconds: float) -> bool:
    """Whether any text value in the rows is a student id, which the column names can miss."""
    values = sorted({value for row in rows for value in row if isinstance(value, str)})
    if not values:
        return False
    marker = "?" if backend.param_style == "qmark" else "%s"
    placeholders = ", ".join([marker] * len(values))
    sql = f"SELECT student_id FROM student WHERE student_id IN ({placeholders})"
    return bool(backend.execute(sql, values, 1, timeout_seconds).rows)


def _group_size(value) -> float:
    """The count as a number. Anything that isn't one counts as 0, so its row is dropped."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return value
