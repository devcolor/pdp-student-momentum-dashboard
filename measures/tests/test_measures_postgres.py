"""Runs the same checks on PostgreSQL when PDP_TEST_POSTGRES_URL points at a server.

With PDP_REQUIRE_POSTGRES=1 (CI sets it) a missing server or psycopg fails instead of skipping.
"""
import os
from pathlib import Path

import pytest

from measures.models import Cohort, GroupBy, GroupDimension, Measure, Status
from measures.run_measures import COMPLEMENT_NOTE, MEASURES, groups_for, read_open_values, run_measure

FIXTURE = Path(__file__).parent / "fixture.sql"
SCHEMA = f"measures_test_{os.getpid()}"  # one per worker process, so parallel tests never share it or touch the data model's tables


def give_up(reason: str) -> None:
    """Skip the test, or fail it when PostgreSQL is required."""
    if os.environ.get("PDP_REQUIRE_POSTGRES") == "1":
        pytest.fail(f"PDP_REQUIRE_POSTGRES=1, but {reason}")
    pytest.skip(reason)


@pytest.fixture
def pg_database():
    """The tiny database in its own PostgreSQL schema, dropped afterwards."""
    url = os.environ.get("PDP_TEST_POSTGRES_URL")
    if not url:
        give_up("PDP_TEST_POSTGRES_URL is not set")
    try:
        import psycopg
    except ImportError:
        give_up("psycopg is not installed")
    connection = psycopg.connect(url, autocommit=True)
    connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    connection.execute(f"CREATE SCHEMA {SCHEMA}")
    connection.execute(f"SET search_path TO {SCHEMA}")
    connection.execute(FIXTURE.read_text(encoding="utf-8"))
    yield connection
    connection.execute(f"DROP SCHEMA {SCHEMA} CASCADE")
    connection.close()


def find(results, label):
    """The one row whose group has this label."""
    rows = [r for r in results if r.group.label == label]
    assert len(rows) == 1, label
    return rows[0]


def counted(database, measure, cohort, *dimensions):
    """The calculation's (numerator, denominator) per group label, before any group is hidden.

    For checking the arithmetic on groups the tiny database is too small to show.
    """
    group_by = [GroupBy.of(*dimensions)]
    groups = groups_for(group_by, read_open_values(database, MEASURES[measure], [cohort], group_by))
    counts = MEASURES[measure].count(database, [cohort], groups)
    return {group.label: (counts[(cohort, group)].numerator, counts[(cohort, group)].denominator) for group in groups}


def test_retention_and_persistence_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    retention = find(run_measure(Measure.RETENTION, [cohort], database=pg_database), "everyone")
    assert (retention.numerator, retention.denominator, retention.n_excluded) == (16, 20, 4)
    persistence = find(run_measure(Measure.PERSISTENCE, [cohort], database=pg_database), "everyone")
    assert (persistence.numerator, persistence.denominator) == (5, 20)


def test_groups_and_pooling_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    assert counted(pg_database, Measure.RETENTION, cohort, GroupDimension.COHORT_TERM)["cohort_term=Fall"] == (14, 14)
    assert counted(pg_database, Measure.RETENTION, cohort, GroupDimension.AGE_BAND)["age_band=> 20-24"][1] == 12

    pooled = run_measure(Measure.RETENTION, [Cohort.of("2022-23", "2023-24")], database=pg_database)
    assert (pooled[0].numerator, pooled[0].denominator) == (22, 32)

    unseen = run_measure(Measure.RETENTION, [Cohort.of("2024-25")], database=pg_database)
    assert unseen[0].status == Status.NOT_YET_OBSERVABLE

    # A pool that includes a year with no answers yet can't be read yet either.
    partly = run_measure(Measure.RETENTION, [Cohort.of("2023-24", "2024-25")], database=pg_database)
    assert partly[0].status == Status.NOT_YET_OBSERVABLE

    # Blank and unlisted values count as UNKNOWN: pell 'U' for students 45 to 48.
    by_pell = run_measure(Measure.RETENTION, [Cohort.of("2024-25")], [GroupBy.of(GroupDimension.PELL)], database=pg_database)
    assert find(by_pell, "pell=UNKNOWN").status == Status.NOT_YET_OBSERVABLE


def test_gateway_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    math = find(run_measure(Measure.GATEWAY_MATH, [cohort], database=pg_database), "everyone")
    assert (math.numerator, math.denominator) == (12, 20)
    english = find(run_measure(Measure.GATEWAY_ENGLISH, [cohort], database=pg_database), "everyone")
    assert (english.numerator, english.denominator) == (10, 24)


def test_dfw_on_postgres(pg_database):
    row = find(run_measure(Measure.DFW_RATE, [Cohort.of("2022-23")], database=pg_database), "everyone")
    assert (row.numerator, row.denominator, row.n_excluded) == (10, 25, 2)


def test_credit_completion_on_postgres(pg_database):
    # PostgreSQL sums the ratios as decimals. They must come back as the same numbers as on SQLite.
    row = find(run_measure(Measure.CREDIT_COMPLETION, [Cohort.of("2022-23")], database=pg_database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate, row.n_excluded) == (11, 18, 0.6111, 4)


def test_dfw_by_course_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    assert counted(pg_database, Measure.DFW_RATE, cohort, GroupDimension.COURSE)["course=ENGL 1302"] == (7, 22)
    # MATH 1314 has 3 students, so ENGL 1302 is hidden as its cover, on PostgreSQL as on SQLite.
    results = run_measure(Measure.DFW_RATE, [cohort], [GroupBy.of(GroupDimension.COURSE)], database=pg_database)
    assert find(results, "course=ENGL 1302").note.endswith(COMPLEMENT_NOTE)


def test_first_fall_measures_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    retention = find(run_measure(Measure.FALL_TO_SPRING_RETENTION, [cohort], database=pg_database), "everyone")
    assert (retention.numerator, retention.denominator, retention.n_excluded, retention.n_out_of_scope) == (8, 10, 2, 12)
    standing = find(run_measure(Measure.FIRST_FALL_GOOD_STANDING, [cohort], database=pg_database), "everyone")
    assert (standing.numerator, standing.denominator, standing.n_excluded) == (7, 10, 2)


def test_midterm_measures_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    alert = find(run_measure(Measure.MIDTERM_ALERT_RATE, [cohort], database=pg_database), "everyone")
    assert (alert.numerator, alert.denominator, alert.n_excluded, alert.n_out_of_scope) == (11, 22, 4, 1)
    assert counted(pg_database, Measure.MIDTERM_ALERT_RATE, cohort, GroupDimension.COURSE)["course=ENGL 1302"] == (11, 22)
    recovery = find(run_measure(Measure.MIDTERM_RECOVERY_RATE, [cohort], database=pg_database), "everyone")
    assert (recovery.numerator, recovery.denominator, recovery.n_excluded) == (4, 10, 1)


def test_affinity_and_educational_goal_on_postgres(pg_database):
    cohort = Cohort.of("2022-23")
    affinity = counted(pg_database, Measure.RETENTION, cohort, GroupDimension.AFFINITY)
    assert (affinity["affinity=None"], affinity["affinity=Student Government"]) == ((12, 12), (0, 4))
    goal = counted(pg_database, Measure.RETENTION, cohort, GroupDimension.EDUCATIONAL_GOAL)
    assert (goal["educational_goal=graduate_and_transfer"], goal["educational_goal=UNKNOWN"]) == ((6, 6), (2, 6))


def test_unmet_need_band_with_the_enrollment_measures_on_postgres(pg_database):
    # The same counts as SQLite: DFW's enrollments aren't repeated by the aid join.
    cohort = Cohort.of("2022-23")
    dfw = counted(pg_database, Measure.DFW_RATE, cohort, GroupDimension.UNMET_NEED_BAND)
    assert (dfw["unmet_need_band=$5k+"], dfw["unmet_need_band=UNKNOWN"]) == ((3, 6), (1, 2))
    assert sum(denominator for label, (_, denominator) in dfw.items() if label != "everyone") == 25
    credit = counted(pg_database, Measure.CREDIT_COMPLETION, cohort, GroupDimension.UNMET_NEED_BAND)
    assert credit["unmet_need_band=$1-2k"][1] == 4


def test_publish_on_postgres(pg_database, tmp_path):
    import json
    import sqlite3

    from measures.publish import file_sha256, publication_path, publish

    # The loader makes loaded_at a TIMESTAMP on PostgreSQL, so psycopg reads it back as a datetime.
    pg_database.execute("ALTER TABLE data_provider ALTER COLUMN loaded_at TYPE TIMESTAMP USING loaded_at::timestamp")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("version: 1\ncohorts: [['2022-23']]\nmeasures: {retention: [[pell]], dfw_rate: [[course]]}\n",
                        encoding="utf-8")
    results = tmp_path / "success_measures.sqlite"
    record = publish(pg_database, results, manifest)

    assert record["manifest_version"] == 1
    assert record["results_sha256"] == file_sha256(results)
    # The same string SQLite gives, in the record and in both tables.
    assert record["data_loaded_at"] == "2026-01-01T00:00:00"
    assert json.loads(publication_path(results).read_text())["data_loaded_at"] == "2026-01-01T00:00:00"
    with sqlite3.connect(results) as connection:
        for table in ("success_measures", "equity_gaps"):
            loaded = {row[0] for row in connection.execute(f"SELECT DISTINCT data_loaded_at FROM {table}")}
            assert loaded == {"2026-01-01T00:00:00"}, table


def test_publish_on_postgres_names_a_missing_table(pg_database, tmp_path):
    from measures.publish import publish

    pg_database.execute("DROP TABLE student_term_matrix")
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("version: 1\ncohorts: [['2022-23']]\nmeasures: {retention: [[pell]]}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="student_term_matrix"):
        publish(pg_database, tmp_path / "out.sqlite", manifest)
