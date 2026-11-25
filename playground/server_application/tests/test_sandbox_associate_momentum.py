"""Known-answer tests for associate momentum, through the read-only query path and gap finder."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.chat import query_tool

BASE = "/api/v1/sandbox/associate-momentum"

SCHEMA = """
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, credit_years_observed INTEGER,
    credential_type_sought_year_1 TEXT,
    number_of_credits_earned_yr_1 REAL, number_of_credits_earned_yr_2 REAL,
    number_of_credits_earned_yr_3 REAL, number_of_credits_earned_yr_4 REAL,
    first_year_to_associates_at_coho INTEGER, first_year_to_a_or_c_at_other INTEGER,
    first_year_to_bachelor_at_other INTEGER, years_of_last_enrollment_at_coho INTEGER,
    enrollment_intensity_first_term TEXT
);
"""

# credit_years_observed counts the year still under way, so these have had 3, 2 and 1 full years.
OBSERVED = {"2021-22": 4, "2022-23": 3, "2023-24": 2}
NO_CREDITS = (None, None, None, None)


def _students(
    prefix: str,
    count: int,
    cohort: str,
    credits: tuple[float | None, ...],
    associate: int = 0,
    elsewhere: int = 0,
    bachelor_elsewhere: int = 0,
    last_enrolled: int = 2,
    intensity: str | None = "Full-Time",
    sought: str = "A",
) -> list[tuple]:
    """`count` students alike, as cohort_membership rows. `credits` is years 1 to 4 earned."""
    return [
        (
            f"{prefix}{i}",
            cohort,
            OBSERVED[cohort],
            sought,
            *credits,
            associate,
            elsewhere,
            bachelor_elsewhere,
            last_enrolled,
            intensity,
        )
        for i in range(count)
    ]


# Credits by year 2 are in the comment on each line; year 3 adds nothing in 2021-22.
STUDENTS = [
    # 2021-22: 96 associate-seekers, 94 with every credit year recorded. 3 full years.
    *_students("a", 12, "2021-22", (31, 31, 0, 0), associate=2),  # 62
    *_students("b", 10, "2021-22", (20, 30, 0, 0), last_enrolled=3),  # 50, near
    *_students("c", 11, "2021-22", (24, 32, 0, 0), intensity="Part-Time"),  # 56, near
    *_students("d", 3, "2021-22", (30, 32, 0, 0), elsewhere=2),  # 62, credential elsewhere
    *_students("e", 4, "2021-22", (25, 25, 0, 0), bachelor_elsewhere=1, last_enrolled=1),  # 50
    *_students("f", 15, "2021-22", (20, 15, 0, 0)),  # 35
    *_students("g", 5, "2021-22", (20, 15, 0, 0), associate=2),  # 35, associate anyway
    *_students("h", 15, "2021-22", (10, 10, 0, 0), intensity="Part-Time"),  # 20
    *_students("i", 14, "2021-22", (6, 0, 0, 0), last_enrolled=1, intensity="Part-Time"),  # 6
    *_students("j", 5, "2021-22", (30, 20, 0, 0), associate=3, last_enrolled=3),  # 50, near by 2
    *_students("k", 2, "2021-22", NO_CREDITS, last_enrolled=1),  # credits missing
    *_students("l", 15, "2021-22", (30, 30, 0, 0), associate=2, sought="C1"),  # not seekers
    # 2022-23: 66 associate-seekers, 65 with years 1 and 2 recorded. 2 full years.
    *_students("m", 10, "2022-23", (30, 30, 0, None), associate=2),  # 60
    *_students("n", 25, "2022-23", (10, 10, 0, None), intensity="Part-Time"),  # 20
    *_students("o", 12, "2022-23", (24, 24, 0, None)),  # 48, near
    *_students("p", 3, "2022-23", (0, 0, 0, None), last_enrolled=1, intensity=None),  # 0
    *_students("q", 4, "2022-23", (30, 25, 0, None), last_enrolled=3, intensity=None),  # 55, near
    *_students("r", 1, "2022-23", (20, None, None, None), last_enrolled=1),  # year 2 missing
    *_students("s", 11, "2022-23", (32, 32, 0, None), last_enrolled=3),  # 64, near
    # 2023-24: 1 full year, so too new for every view on this page.
    *_students("t", 10, "2023-24", (40, 30, None, None)),
]


def _load(path: Path, students: list[tuple], monkeypatch: pytest.MonkeyPatch) -> None:
    """Write the students to a small data model and point the read-only backend at it."""
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany(
        f"INSERT INTO cohort_membership VALUES ({', '.join('?' * 13)})", students
    )
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


@pytest.fixture
def model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the read-only backend at a small data model with known counts."""
    _load(tmp_path / "model.db", STUDENTS, monkeypatch)


@pytest.mark.usefixtures("model_db")
def test_milestones_count_seekers_with_credits_and_name_the_biggest_drop(
    client: TestClient,
) -> None:
    body = client.get(f"{BASE}/milestones", params={"window": "2"}).json()

    assert body["meta"]["source"] == "synthetic"
    assert "Too new, left out: 2023-24" in body["meta"]["filters"]
    assert [
        (r["cohort"], r["milestone"], r["status"], r["reached"], r["n"], r["rate"])
        for r in body["rows"]
    ] == [
        ("2021-22", "15 credits", "ok", 80, 94, 85.1),
        ("2021-22", "30 credits", "ok", 65, 94, 69.1),
        ("2021-22", "45 credits", "ok", 45, 94, 47.9),
        ("2021-22", "60 credits", "ok", 15, 94, 16.0),
        ("2021-22", "Earned the associate", "ok", 17, 94, 18.1),
        # 62 of 65 reached 15 credits: the 3 who didn't would show, so the share is hidden.
        ("2022-23", "15 credits", "suppressed", None, 65, None),
        ("2022-23", "30 credits", "ok", 37, 65, 56.9),
        ("2022-23", "45 credits", "ok", 37, 65, 56.9),
        ("2022-23", "60 credits", "ok", 21, 65, 32.3),
        ("2022-23", "Earned the associate", "ok", 10, 65, 15.4),
    ]
    assert body["meta"]["takeaway"] == (
        "Within 2 years, associate-seekers in the 2022-23 cohort drop off most between 15 and 30 "
        "credits: all but fewer than 10 reached 15 credits, 56.9% reached 30, 56.9% reached 45 "
        "and 32.3% reached 60; 15.4% earned the associate, fewer than reached 60 credits here."
    )


@pytest.mark.usefixtures("model_db")
def test_near_completers_hide_a_second_part_so_a_small_one_cannot_be_subtracted(
    client: TestClient,
) -> None:
    body = client.get(f"{BASE}/near-completers", params={"window": "2"}).json()

    parts = [
        "45 to under 54: about a term short",
        "54 to under 60: 1 or 2 courses short",
        "60 or more: enough credits, no degree",
    ]
    assert [
        (
            r["cohort"],
            r["part"],
            r["count"],
            r["share_of_pool"],
            r["pool"],
            r["seekers"],
            r["pool_rate"],
        )
        for r in body["rows"]
    ] == [
        # No one has 60 or more: a hidden zero gives nothing away, so nothing else is hidden.
        ("2021-22", parts[0], 15, 57.7, 26, 94, 27.7),
        ("2021-22", parts[1], 11, 42.3, 26, 94, 27.7),
        ("2021-22", parts[2], None, None, 26, 94, 27.7),
        # 4 are 1 or 2 courses short, so the next smallest part (11) is hidden with them.
        ("2022-23", parts[0], 12, 44.4, 27, 65, 41.5),
        ("2022-23", parts[1], None, None, 27, 65, 41.5),
        ("2022-23", parts[2], None, None, 27, 65, 41.5),
    ]
    assert body["meta"]["takeaway"] == (
        "Within 2 years, near-completers were 27.7% of associate-seekers in 2021-22 (26) and "
        "41.5% in 2022-23 (27), no clear change; in 2022-23, the share who already had 60 or more "
        "credits is hidden to keep small groups private."
    )


@pytest.mark.usefixtures("model_db")
def test_near_completers_by_enrollment_name_the_share_who_stopped(client: TestClient) -> None:
    body = client.get(
        f"{BASE}/near-completers", params={"window": "2", "split": "enrollment"}
    ).json()

    assert [(r["cohort"], r["part"], r["count"], r["share_of_pool"]) for r in body["rows"]] == [
        ("2021-22", "Enrolled here after year 2", 15, 57.7),
        ("2021-22", "Not enrolled here after year 2", 11, 42.3),
        ("2022-23", "Enrolled here after year 2", 15, 55.6),
        ("2022-23", "Not enrolled here after year 2", 12, 44.4),
    ]
    assert body["meta"]["takeaway"].endswith(
        "; in 2022-23, 44.4% of them had not enrolled here after year 2."
    )


@pytest.mark.usefixtures("model_db")
def test_near_completers_on_one_cohort_drop_those_who_finished_by_then(
    client: TestClient,
) -> None:
    body = client.get(
        f"{BASE}/near-completers", params={"window": "3", "split": "intensity"}
    ).json()

    # The 5 who earned the associate in year 3 are near-completers by year 2 but not by year 3.
    assert [
        (r["cohort"], r["part"], r["count"], r["pool"], r["pool_rate"]) for r in body["rows"]
    ] == [
        ("2021-22", "Full-time", 10, 21, 22.3),
        ("2021-22", "Part-time", 11, 21, 22.3),
    ]
    assert body["meta"]["filters"][2] == "Too new, left out: 2022-23, 2023-24"
    assert body["meta"]["takeaway"] == (
        "Within 3 years, near-completers were 22.3% of associate-seekers in 2021-22 (21); in "
        "2021-22, 52.4% of them started part-time."
    )


@pytest.mark.usefixtures("model_db")
def test_year_one_bands_compare_with_everyone_else_through_the_gap_finder(
    client: TestClient,
) -> None:
    body = client.get(f"{BASE}/year-one", params={"window": "2"}).json()

    assert body["everyone_rate"] == 16.7
    assert [
        (
            r["group"],
            r["status"],
            r["earned"],
            r["n"],
            r["rate"],
            r["comparison_rate"],
            r["gap_pts"],
            r["likely_noise"],
        )
        for r in body["rows"]
    ] == [
        ("Under 12 credits", "ok", 0, 57, 0.0, 25.7, -25.71, False),
        ("12 to under 24 credits", "ok", 5, 31, 16.1, 16.8, -0.66, True),
        ("24 to under 30 credits", "ok", 0, 27, 0.0, 20.0, -20.0, False),
        ("30 or more credits", "ok", 22, 45, 48.9, 4.3, 44.62, False),
        # The 2 students with no year-1 credits are too few to show.
        ("Not recorded", "suppressed", None, None, None, None, None, None),
    ]
    assert body["meta"]["takeaway"] == (
        "Among associate-seekers in the 2021-22 + 2022-23 cohorts, the associate within 2 years "
        "rises from 0.0% (under 12 credits in year 1) to 48.9% (30 or more credits); the clearest "
        'gap is "30 or more credits", 48.9% against 4.3% for everyone else (+44.6 points).'
    )


def test_a_model_with_only_new_cohorts_says_there_is_nothing_to_show(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    newest_only = [row for row in STUDENTS if row[1] == "2023-24"]
    _load(tmp_path / "new.db", newest_only, monkeypatch)

    for path in ("/milestones", "/near-completers", "/year-one"):
        body = client.get(f"{BASE}{path}", params={"window": "2"}).json()
        assert body["rows"] == []
        assert body["meta"]["takeaway"] == (
            "No cohort has had 2 years in full yet, so there's nothing to show."
        )


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/milestones", {"window": "1"}),
        ("/near-completers", {"split": "program"}),
        ("/near-completers", {"window": "4"}),
        ("/year-one", {"window": "so_far"}),
    ],
)
def test_unknown_filters_are_refused(client: TestClient, path: str, params: dict) -> None:
    assert client.get(f"{BASE}{path}", params=params).status_code == 422


def test_a_data_model_that_cannot_be_read_is_a_503(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=tmp_path / "missing.db"))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)

    response = client.get(f"{BASE}/near-completers")

    assert response.status_code == 503
    assert "Load it from the Sandbox pipeline page" in response.text
