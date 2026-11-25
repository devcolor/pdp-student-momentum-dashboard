"""Known-answer tests for enrollment trends, run through the real read-only query path."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.chat import query_tool
from app.sandbox.enrollment_trends import kpis

ENTERING = "/api/v1/sandbox/enrollment-trends/entering"
BY_TERM = "/api/v1/sandbox/enrollment-trends/by-term"
KPIS = "/api/v1/sandbox/enrollment-trends/kpis"

SCHEMA = """
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, cohort_term TEXT, enrollment_type TEXT,
    enrollment_intensity_first_term TEXT, pell_status_first_year TEXT
);
CREATE TABLE term (term_id INTEGER, academic_year TEXT, academic_term TEXT, sort_order INTEGER);
CREATE TABLE course_enrollment (student_id TEXT, cohort TEXT, term_id INTEGER, course_id INTEGER);
CREATE TABLE student (
    student_id TEXT, student_age TEXT, race TEXT, ethnicity TEXT, gender TEXT, first_gen TEXT
);
CREATE TABLE data_provider (
    provider_id INTEGER, source_file TEXT, file_sha256 TEXT, loaded_at TEXT
);
INSERT INTO data_provider VALUES (1, 'test', 'not-a-real-hash', '2026-01-01T00:00:00');
"""


def _add_students(connection: sqlite3.Connection) -> None:
    """A student row for every cohort member: the shared make-up measures join the two."""
    connection.execute(
        "INSERT INTO student SELECT DISTINCT student_id, 'Older than 24', 'White', 'N', 'F', NULL "
        "FROM cohort_membership"
    )


FALL_21, SPRING_22, SUMMER_22, FALL_22, UNKNOWN_TERM, FALL_20, SPRING_23 = 1, 2, 3, 4, 5, 6, 7
TERMS = [
    (FALL_20, "2020-21", "FALL", 0),
    (FALL_21, "2021-22", "FALL", 1),
    (SPRING_22, "2021-22", "SPRING", 2),
    (SUMMER_22, "2021-22", "SUMMER", 3),
    (FALL_22, "2022-23", "FALL", 4),
    (SPRING_23, "2022-23", "SPRING", 5),
    (UNKNOWN_TERM, "UNKNOWN", "UNKNOWN", 6),
]


def _members(prefix: str, count: int, cohort: str, entry_type: str | None) -> list[tuple]:
    """Build cohort rows for `count` students of one entry type."""
    return [(f"{prefix}{i}", cohort, "FALL", entry_type, "Full-Time", "Y") for i in range(count)]


def _courses(prefix: str, count: int, cohort: str, term_id: int, course_id: int | None) -> list:
    """Build one course row per student for one term."""
    return [(f"{prefix}{i}", cohort, term_id, course_id) for i in range(count)]


@pytest.fixture
def model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the read-only backend at a small data model with known counts."""
    path = tmp_path / "model.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany("INSERT INTO term VALUES (?, ?, ?, ?)", TERMS)
    members = [
        *_members("a", 30, "2021-22", "First-Time"),
        *_members("b", 10, "2021-22", "Transfer-In"),
        *_members("c", 3, "2021-22", "Re-admit"),
        *_members("d", 30, "2022-23", "First-Time"),
        *_members("e", 30, "2022-23", "Transfer-In"),
    ]
    connection.executemany("INSERT INTO cohort_membership VALUES (?, ?, ?, ?, ?, ?)", members)
    _add_students(connection)
    courses = [
        *_courses("a", 30, "2021-22", FALL_21, 1),
        *_courses("a", 30, "2021-22", FALL_21, 2),  # a second course: still one student
        *_courses("a", 20, "2021-22", SPRING_22, 1),
        *_courses("a", 20, "2021-22", SUMMER_22, 1),  # summer: left out
        *_courses("b", 10, "2021-22", SPRING_22, None),  # enrolled elsewhere: left out
        *_courses("e", 4, "2022-23", SPRING_23, 1),  # under 10: suppressed
        *_courses("a", 12, "2021-22", FALL_22, 1),
        *_courses("d", 25, "2022-23", FALL_22, 1),
        *_courses("d", 15, "2022-23", FALL_21, 1),  # before the cohort year: left out
        *_courses("d", 15, "2022-23", FALL_20, 1),  # before the cohort year: left out
        *_courses("e", 15, "2022-23", UNKNOWN_TERM, 1),  # unknown term: left out
    ]
    connection.executemany("INSERT INTO course_enrollment VALUES (?, ?, ?, ?)", courses)
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


@pytest.mark.usefixtures("model_db")
def test_entering_returns_exact_counts_shares_and_suppression(client: TestClient) -> None:
    body = client.get(ENTERING, params={"split_by": "enrollment_type"}).json()

    assert body["meta"]["source"] == "synthetic"
    assert body["meta"]["takeaway"] == (
        "Transfer-In moved the most: 23.3% of 2021-22 entrants to 50.0% of 2022-23 entrants."
    )
    assert body["rows"] == [
        {"cohort": "2021-22", "group": "First-Time", "n": 30, "share": 69.8, "cohort_total": 43},
        {"cohort": "2021-22", "group": "Transfer-In", "n": 10, "share": 23.3, "cohort_total": 43},
        {"cohort": "2021-22", "group": "Re-admit", "n": None, "share": None, "cohort_total": 43},
        {"cohort": "2022-23", "group": "First-Time", "n": 30, "share": 50.0, "cohort_total": 60},
        {"cohort": "2022-23", "group": "Transfer-In", "n": 30, "share": 50.0, "cohort_total": 60},
    ]


@pytest.mark.usefixtures("model_db")
def test_by_term_counts_students_once_and_leaves_out_other_terms(client: TestClient) -> None:
    body = client.get(BY_TERM).json()

    assert body["meta"]["source"] == "synthetic"
    assert body["rows"] == [
        {"term": "Fall 21", "cohort": "2021-22", "n": 30, "term_total": 30},
        {"term": "Spr 22", "cohort": "2021-22", "n": 20, "term_total": 20},
        {"term": "Fall 22", "cohort": "2021-22", "n": 12, "term_total": 37},
        {"term": "Fall 22", "cohort": "2022-23", "n": 25, "term_total": 37},
        {"term": "Spr 23", "cohort": "2022-23", "n": None, "term_total": 4},
    ]


@pytest.fixture
def kpi_model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A small data model where every KPI tile clears the display minimum."""
    path = tmp_path / "kpi_model.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany("INSERT INTO term VALUES (?, ?, ?, ?)", TERMS)
    first_time = ("FALL", "First-Time", "Full-Time", "Y")
    transfer = ("FALL", "Transfer-In", "Part-Time", "Y")
    members = [
        *[(f"a{i}", "2021-22", *first_time) for i in range(30)],
        *[(f"b{i}", "2021-22", *transfer) for i in range(10)],
        *[(f"c{i}", "2022-23", *first_time) for i in range(30)],
        *[(f"d{i}", "2022-23", *transfer) for i in range(20)],
    ]
    connection.executemany("INSERT INTO cohort_membership VALUES (?, ?, ?, ?, ?, ?)", members)
    _add_students(connection)
    courses = [
        *_courses("a", 20, "2021-22", FALL_21, 1),
        *_courses("a", 20, "2021-22", FALL_21, 2),  # a second course: still one student
        *_courses("a", 15, "2021-22", SPRING_22, 1),
        *_courses("a", 12, "2021-22", FALL_22, 1),  # a later year: not the cohort's first fall
        *_courses("c", 30, "2022-23", FALL_22, 1),
        *_courses("c", 24, "2022-23", SPRING_23, 1),
        *_courses("d", 20, "2022-23", SPRING_23, 1),  # spring starters: not in the denominator
    ]
    connection.executemany("INSERT INTO course_enrollment VALUES (?, ?, ?, ?)", courses)
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


@pytest.mark.usefixtures("kpi_model_db")
def test_kpis_return_latest_cohort_with_trends(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fall-to-spring is the shared measure, planted here: 75% then 80%.
    planted = {"2021-22": (15, 20), "2022-23": (24, 30)}
    monkeypatch.setattr(kpis, "_fall_to_spring_counts", lambda cohorts: planted)
    body = client.get(KPIS).json()

    assert body["meta"]["source"] == "synthetic"
    assert body["meta"]["filters"][0] == "2022-23 cohort"
    tiles = {item["id"]: item for item in body["items"]}
    assert list(tiles) == [
        "entering_students",
        "transfer_share",
        "part_time_share",
        "fall_to_spring",
    ]

    assert tiles["entering_students"]["unit"] == "count"
    assert tiles["entering_students"]["value"] == 50
    assert tiles["entering_students"]["trend"] == {
        "direction": "up",
        "status": "good",
        "label": "+25.0% vs 2021-22",
    }
    assert tiles["transfer_share"]["value"] == 40.0
    assert tiles["transfer_share"]["trend"]["label"] == "+60.0% vs 2021-22"
    # A rising transfer-in share is good, so its pill is green.
    assert tiles["transfer_share"]["trend"]["status"] == "good"
    assert tiles["part_time_share"]["value"] == 40.0
    assert tiles["fall_to_spring"]["value"] == 80.0
    assert tiles["fall_to_spring"]["detail"].startswith("24 of 30 ")
    assert tiles["fall_to_spring"]["trend"] == {
        "direction": "up",
        "status": "good",
        "label": "+6.7% vs 2021-22",
    }


@pytest.mark.usefixtures("model_db")
def test_kpis_leave_out_tiles_under_the_display_minimum(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(kpis, "_fall_to_spring_counts", lambda cohorts: {})
    body = client.get(KPIS).json()

    # No part-time students, and none of the first-fall students took a spring course.
    assert [item["id"] for item in body["items"]] == ["entering_students", "transfer_share"]


def test_entering_rejects_an_unknown_split(client: TestClient) -> None:
    response = client.get(ENTERING, params={"split_by": "student_id"})

    assert response.status_code == 422
