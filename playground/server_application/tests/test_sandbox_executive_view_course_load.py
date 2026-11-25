"""Known-answer tests for the executive view's year-1 course load curve and its filters.

The model is a handful of students, so every count below can be checked by hand.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.chat import query_tool
from app.sandbox.executive_view import course_load
from app.sandbox.executive_view.course_load import band_labels

PATH = "/api/v1/sandbox/executive-view/course-load"
BANDS = band_labels(3)  # The default granularity.

SCHEMA = """
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, credential_type_sought_year_1 TEXT,
    program_of_study_year_1 TEXT, pell_status_first_year TEXT,
    number_of_credits_attempted_yr_1 REAL
);
CREATE TABLE student (
    student_id TEXT, race TEXT, gender TEXT, student_age TEXT, first_gen TEXT
);
"""


def _students(
    prefix: str,
    count: int,
    cohort: str,
    sought: str,
    credits: float | None,
    gender: str,
    race: str = "White",
) -> list[tuple[tuple, tuple]]:
    """`count` students alike, each as a (cohort_membership row, student row) pair."""
    return [
        (
            (f"{prefix}{i}", cohort, sought, "240101", "N", credits),
            (f"{prefix}{i}", race, gender, "20 and younger", None),
        )
        for i in range(count)
    ]


# 2024-25, outside the pool, has 54 students with credits. Each line names the band its students
# land in. Filters on a single pooled year show no live curve, so the filter tests use 2024-25.
STUDENTS = [
    *_students("a12-", 20, "2024-25", "A", 12, "F"),  # 12-14
    *_students("a30-", 10, "2024-25", "A", 30, "F"),  # 30-32: on track
    *_students("c6-", 15, "2024-25", "C1", 6, "M"),  # 6-8
    *_students("c3-", 5, "2024-25", "C1", 3, "M"),  # 3-5: under 10, hidden
    *_students("nc-", 4, "2024-25", "NC", 9, "M", race="Hispanic"),  # 9-11: under 10, hidden
    *_students("none-", 2, "2024-25", "A", None, "F"),  # no credits recorded: left out
    *_students("zero-", 1, "2024-25", "A", 0, "F"),  # 0 credits: left out
    *_students("prev-", 10, "2023-24", "A", 15, "F"),  # 15-17, the cohort before: in the pool
]


def _band(label: str) -> int:
    """Where a band sits in the response's lists."""
    return BANDS.index(label)


@pytest.fixture
def model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the students to a small data model and point the read-only backend at it."""
    path = tmp_path / "model.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany(
        "INSERT INTO cohort_membership VALUES (?, ?, ?, ?, ?, ?)", [row for row, _ in STUDENTS]
    )
    connection.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?)", [s for _, s in STUDENTS])
    connection.commit()
    connection.close()
    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


@pytest.mark.usefixtures("model_db")
def test_with_no_filter_the_curve_is_everyone_and_small_bands_are_hidden(
    client: TestClient,
) -> None:
    body = client.get(PATH, params={"cohort": "2024-25"}).json()
    everyone = body["everyone"]

    assert body["meta"]["source"] == "synthetic"
    assert body["bands"][0] == "0-2" and body["bands"][-1] == "36+"
    assert body["on_track_band"] == "30-32"
    assert body["selected"] is None and body["hidden_reason"] is None
    assert everyone["n"] == 54
    assert everyone["median_credits"] == 12.0
    assert everyone["under_12_pct"] == 44.4  # 24 of 54
    assert everyone["on_track_pct"] == 18.5  # 10 of 54
    assert everyone["shares"][_band("6-8")] == 27.8
    assert everyone["shares"][_band("12-14")] == 37.0
    assert everyone["shares"][_band("30-32")] == 18.5
    # Two bands under 10 are hidden as null, never 0. Two hidden can't be told apart from the total.
    assert everyone["shares"][_band("3-5")] is None
    assert everyone["shares"][_band("9-11")] is None
    assert everyone["shares"][_band("15-17")] == 0.0
    assert body["meta"]["definitions"]["Left out"].startswith("Fewer than 10 students")


@pytest.mark.usefixtures("model_db")
def test_a_goal_filter_draws_the_matching_students(client: TestClient) -> None:
    body = client.get(PATH, params={"cohort": "2024-25", "goal": "associate"}).json()
    selected = body["selected"]

    assert selected["n"] == 30
    assert selected["shares"][_band("12-14")] == 66.7
    assert selected["shares"][_band("30-32")] == 33.3
    assert selected["under_12_pct"] is None  # 0 under 12 would reveal a count under 10
    assert selected["on_track_pct"] == 33.3
    assert body["everyone"]["n"] == 54
    assert "Goal: Associate-seekers" in body["meta"]["filters"]
    assert "Credential Type Sought Year 1" in body["meta"]["fields_used"]


@pytest.mark.usefixtures("model_db")
def test_a_lone_hidden_band_hides_the_next_smallest_too(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The 9 "other goal" students would make certificate their cover; this test is about bands.
    monkeypatch.setattr(course_load, "_covered", lambda years, active: False)
    selected = client.get(PATH, params={"cohort": "2024-25", "goal": "certificate"}).json()[
        "selected"
    ]

    # 5 students in 3-5 would otherwise be 20 - 15, so 6-8 is hidden with it.
    assert selected["n"] == 20
    assert selected["shares"][_band("3-5")] is None
    assert selected["shares"][_band("6-8")] is None


@pytest.mark.usefixtures("model_db")
def test_filters_combine_and_stack_with_the_cohort_lens(client: TestClient) -> None:
    one = client.get(PATH, params={"cohort": "2024-25", "goal": "associate", "gender": "female"})
    pooled = client.get(PATH, params={"cohort": "all", "goal": "associate", "gender": "female"})

    assert one.json()["selected"]["n"] == 30
    # The pool is 2021-22 to 2023-24, so only the 10 in 2023-24 are in it.
    assert pooled.json()["selected"]["n"] == 10
    assert pooled.json()["meta"]["filters"][0] == "Cohorts 2021-22 to 2023-24, pooled"


@pytest.mark.usefixtures("model_db")
def test_fewer_than_10_matching_students_are_hidden(client: TestClient) -> None:
    body = client.get(PATH, params={"cohort": "2024-25", "goal": "other"}).json()

    assert body["selected"]["n"] is None and set(body["selected"]["shares"]) == {None}
    assert body["hidden_reason"] == "Fewer than 10 students match these filters."
    assert body["meta"]["takeaway"] == body["hidden_reason"]


@pytest.mark.usefixtures("model_db")
def test_filters_that_leave_out_fewer_than_10_are_hidden(client: TestClient) -> None:
    # 50 of 54 are White, so everyone's curve minus this one would show the other 4.
    body = client.get(PATH, params={"cohort": "2024-25", "race": "white"}).json()

    assert body["selected"]["n"] is None
    assert body["hidden_reason"].startswith("These filters leave out fewer than 10")


@pytest.mark.usefixtures("model_db")
def test_program_filter_and_options(client: TestClient) -> None:
    by_code = client.get(PATH, params={"cohort": "2024-25", "program": "240101"}).json()
    none_recorded = client.get(PATH, params={"cohort": "2024-25", "program": "none"}).json()
    options = client.get(f"{PATH}/programs", params={"cohort": "2024-25"}).json()

    assert by_code["selected"]["n"] == 54  # everyone: no one is left out
    assert none_recorded["hidden_reason"] == "Fewer than 10 students match these filters."
    assert options == [{"code": "240101", "label": "24.0101 Liberal arts and general studies"}]


@pytest.mark.usefixtures("model_db")
def test_granularity_changes_the_bands(client: TestClient) -> None:
    by_credit = client.get(PATH, params={"cohort": "2024-25", "granularity": "1"}).json()
    by_six = client.get(PATH, params={"cohort": "2024-25", "granularity": "6"}).json()

    assert len(by_credit["bands"]) == 37 and by_credit["bands"][12] == "12"
    assert by_credit["on_track_band"] == "30"
    assert by_credit["everyone"]["shares"][12] == 37.0  # the 20 students on exactly 12
    assert by_six["bands"] == ["0-5", "6-11", "12-17", "18-23", "24-29", "30-35", "36+"]
    assert by_six["on_track_band"] == "30-35"
    # 6-11 holds the 15 on 6 credits and the 4 on 9: 19 of 54, shown though 9 alone wasn't.
    assert by_six["everyone"]["shares"][1] == 35.2
    assert by_six["everyone"]["under_12_pct"] == 44.4  # the same whatever the bands


@pytest.mark.parametrize(
    "params",
    [{"race": "martian"}, {"program": "12345"}, {"program": "52.0411"}, {"granularity": "2"}],
)
def test_values_outside_the_fixed_lists_are_refused(client: TestClient, params: dict) -> None:
    assert client.get(PATH, params=params).status_code == 422


@pytest.mark.usefixtures("model_db")
def test_a_filter_value_covering_a_lone_hidden_sibling_is_hidden(client: TestClient) -> None:
    """Goal "other" has 9 students in 2024-25, so certificate (20) is hidden as its cover."""
    body = client.get(PATH, params={"cohort": "2024-25", "goal": "certificate"}).json()

    assert body["selected"]["n"] is None
    assert "worked out by subtraction" in body["hidden_reason"]


@pytest.mark.usefixtures("model_db")
def test_a_single_pooled_year_shows_no_matching_curve(client: TestClient) -> None:
    """Beside the pool, a 2023-24 curve could be worked out from the pool minus the other years.

    The 10 associate-seekers in 2023-24 would show otherwise. Everyone's curve still shows.
    """
    body = client.get(PATH, params={"cohort": "2023-24", "goal": "associate"}).json()

    assert body["selected"]["n"] is None and set(body["selected"]["shares"]) == {None}
    assert body["hidden_reason"] == course_load.POOL_YEAR_HIDDEN
    assert body["meta"]["takeaway"] == body["hidden_reason"]
    assert body["everyone"]["n"] == 10
    assert body["everyone"]["shares"][_band("15-17")] == 100.0
    assert "Goal: Associate-seekers" in body["meta"]["filters"]
