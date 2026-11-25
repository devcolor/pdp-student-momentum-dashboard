"""A small published results file for tests: its manifest, rows, and the publish step."""

import json
import shutil
import sqlite3
from pathlib import Path

import yaml

from app.sandbox.chat.repo import import_path

COHORT = "2021-22 + 2022-23 + 2023-24"
MANIFEST = """
version: 1
cohorts:
  - ["2021-22", "2022-23", "2023-24"]
measures:
  gateway_math:
    - [race]
    - [race, gender]
"""

# What the pages on the query builder read: de-aggregation, course outcomes and aid momentum.
# Course outcomes' "all" choices read course x race, course x gender, race and gender (version 6).
PAGES_MANIFEST = """
version: 7
cohorts:
  - ["2021-22", "2022-23", "2023-24"]
measures:
  retention: &yes_or_no
    - [race, gender]
    - [pell]
    - [unmet_need_band]
  persistence: *yes_or_no
  gateway_math: *yes_or_no
  gateway_english: *yes_or_no
  fall_to_spring_retention: *yes_or_no
  first_fall_good_standing: *yes_or_no
  credit_completion: *yes_or_no
  dfw_rate:
    - [race, gender]
    - [course]
    - [course, race, gender]
    - [course, race]
    - [course, gender]
    - [pell]
    - [unmet_need_band]
  midterm_alert_rate:
    - [race, gender]
    - [course]
    - [course, race, gender]
    - [course, race]
    - [course, gender]
    - [race]
    - [gender]
  midterm_recovery_rate:
    - [race, gender]
    - [race]
    - [gender]
"""

# What the executive view reads: the pool and each of its years for the headline measures, by the
# gaps card's one-way breakdowns. The pool also has race x gender, as the real one does.
# Version 7: publish also writes the single years' trends (measure_trends).
EXEC_MANIFEST = """
version: 7
cohorts:
  - ["2021-22", "2022-23", "2023-24"]
measures:
  retention: &pooled
    - [race]
    - [gender]
    - [pell]
    - [age_band]
    - [enrollment_intensity]
    - [race, gender]
  persistence: *pooled
  gateway_math: *pooled
  gateway_english: *pooled
single_cohorts:
  years: ["2021-22", "2022-23", "2023-24"]
  measures:
    retention: &singles
      - [race]
      - [gender]
      - [pell]
      - [age_band]
      - [enrollment_intensity]
    persistence: *singles
    gateway_math: *singles
    gateway_english: *singles
"""

# Tables the publish step checks for that the executive view's small test models don't need.
_UNUSED_TABLES = """
CREATE TABLE IF NOT EXISTS course (course_id TEXT);
CREATE TABLE IF NOT EXISTS course_enrollment (student_id TEXT, course_id TEXT);
CREATE TABLE IF NOT EXISTS midterm_grade (student_id TEXT);
CREATE TABLE IF NOT EXISTS student_attribute (
    student_id TEXT, attribute_key TEXT, attribute_value TEXT, term_id INTEGER, source TEXT
);
"""

import_path("mcp")
from pdp_mcp import results as builder  # noqa: E402


def row(
    dimensions: str,
    values: str,
    rate: float | None,
    n: int | None,
    measure: str = "gateway_math",
    cohort: str = COHORT,
) -> tuple:
    """A success_measures row; a rate of None is a hidden group."""
    hidden = rate is None
    return (
        measure,
        cohort,
        dimensions,
        values,
        None if hidden else round(rate * n),
        n,
        rate,
        int(hidden),
        "suppressed" if hidden else "ok",
        "Gateway math.",
    )


ROWS = [
    row("all", "all", 0.28, 3282),
    row("race", "Asian", 0.31, 120),
    row("race", "Native Hawaiian or Other Pacific Islander", None, None),
    row("gender x race", "M x Black or African American", 0.1474, 190),
]


def gap(
    dimensions: str,
    values: str,
    gap_pts: float | None,
    students_affected: float | None,
    likely_noise: bool = False,
    measure: str = "gateway_math",
    status: str = "ok",
    cohort: str = COHORT,
) -> tuple:
    """An equity_gaps row. The interval is the gap give or take 3 points; q is 0.5 when noise."""
    shown = gap_pts is not None
    return (
        measure,
        cohort,
        dimensions,
        values,
        status,
        gap_pts,
        gap_pts - 3 if shown else None,
        gap_pts + 3 if shown else None,
        (0.5 if likely_noise else 0.001) if shown else None,
        int(likely_noise) if shown else None,
        students_affected,
        None,
    )


def publish(results: Path, manifest: Path, rows: list[tuple], gaps: list[tuple] = ()) -> Path:
    """Write a results file with rows, gaps and a publication record naming it and the manifest."""
    with sqlite3.connect(results) as connection:
        connection.execute(
            "CREATE TABLE success_measures (measure, cohort, group_dimensions, group_values,"
            " numerator, denominator, metric_rate, suppressed, status, note)"
        )
        connection.executemany(
            "INSERT INTO success_measures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
        )
        connection.execute(
            "CREATE TABLE equity_gaps (measure, cohort, group_dimensions, group_values, status,"
            " gap_pts, ci_low, ci_high, q_value, likely_noise, students_affected, rank_by_affected)"
        )
        connection.executemany(
            "INSERT INTO equity_gaps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", gaps
        )
        # Version 7's trend table, empty: these files hold no single cohorts to compare.
        connection.execute(
            "CREATE TABLE measure_trends (kpi, cohort, previous_cohort, group_dimensions,"
            " group_values, relative_pct, direction, judgement, label)"
        )
    connection.close()
    record = {
        "manifest_version": yaml.safe_load(manifest.read_text(encoding="utf-8"))["version"],
        "manifest_sha256": builder.file_sha256(manifest),
        "results_sha256": builder.file_sha256(results),
        "data_loaded_at": "2026-11-09",
    }
    builder.publication_path(results).write_text(json.dumps(record))
    return results


def publish_model(model: Path, manifest: Path, results: Path) -> Path:
    """Publish a small data model with the shared publish step, as python -m measures.publish does.

    The model is copied first, so the tables the step checks for are added to the copy only.
    """
    import_path(".")
    from measures.publish import publish as publish_measures  # type: ignore[import-not-found]

    copy = results.with_name(f"{model.stem}.publishing.db")
    shutil.copyfile(model, copy)
    with sqlite3.connect(copy) as connection:
        connection.executescript(_UNUSED_TABLES)
    connection.close()
    publish_measures(database=copy, results=results, manifest_path=manifest)
    return results
