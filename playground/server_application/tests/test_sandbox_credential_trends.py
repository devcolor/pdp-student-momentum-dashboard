"""Known-answer tests for credential trends, through the read-only query path and gap finder."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.chat import query_tool

BASE = "/api/v1/sandbox/credential-trends"
OTHER = "All other programs, or none recorded"

SCHEMA = """
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, credit_years_observed INTEGER,
    first_year_to_associates_at_coho INTEGER, first_year_to_certificate_at_coh INTEGER,
    program_of_study_year_1 TEXT, credential_type_sought_year_1 TEXT,
    completed_gateway_math_year1 TEXT, completed_gateway_english_year1 TEXT,
    enrollment_intensity_first_term TEXT, enrollment_type TEXT, pell_status_first_year TEXT,
    cohort_term TEXT
);
CREATE TABLE student (student_id TEXT, student_age TEXT);
"""

# credit_years_observed counts the year still under way, so these have had 3, 2 and 1 full years.
OBSERVED = {"2021-22": 4, "2022-23": 3, "2023-24": 2}


def _students(
    prefix: str,
    count: int,
    cohort: str,
    associate: int,
    certificate: int,
    program: str | None,
    sought: str,
    gateway_math: str | None,
    age: str = "Older than 24",
) -> list[tuple[tuple, tuple]]:
    """`count` students alike: their cohort row and their student row."""
    return [
        (
            (
                f"{prefix}{i}",
                cohort,
                OBSERVED[cohort],
                associate,
                certificate,
                program,
                sought,
                gateway_math,
                None,
            )
            + ("Full-Time", "First-Time", "N", "FALL"),
            (f"{prefix}{i}", age),
        )
        for i in range(count)
    ]


STUDENTS = [
    # 2021-22: 40 students, 3 full years.
    *_students("a", 10, "2021-22", 2, 0, "240101", "A", "C"),
    *_students("b", 10, "2021-22", 3, 3, "240101", "A", "C"),  # both in year 3
    *_students("c", 12, "2021-22", 0, 1, "520411", "C1", "NA", age="20 and younger"),
    *_students("d", 8, "2021-22", 0, 0, None, "A", "D"),
    # 2022-23: 50 students, 2 full years.
    *_students("e", 6, "2022-23", 2, 0, "240101", "A", "C"),
    *_students(
        "f", 4, "2022-23", 2, 1, "520201", "A", "D"
    ),  # certificate first, then the associate
    *_students("g", 15, "2022-23", 0, 1, "510801", "C2", "NA"),
    *_students("h", 25, "2022-23", 0, 0, "240101", "A", "D"),
    # 2023-24: 20 students, 1 full year.
    *_students("i", 3, "2023-24", 0, 1, "520411", "C1", None),
    *_students("j", 2, "2023-24", 1, 0, "240101", "A", None),
    *_students("k", 15, "2023-24", 0, 0, None, "A", "D"),
]


@pytest.fixture
def model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the read-only backend at a small data model with known counts."""
    path = tmp_path / "model.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany(
        f"INSERT INTO cohort_membership VALUES ({', '.join('?' * 13)})", [m for m, _ in STUDENTS]
    )
    connection.executemany("INSERT INTO student VALUES (?, ?)", [s for _, s in STUDENTS])
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


def _rates(body: dict) -> list[tuple]:
    """(cohort, credential, status, earned, n, rate) for each row."""
    return [
        (r["cohort"], r["credential"], r["status"], r["earned"], r["n"], r["rate"])
        for r in body["rows"]
    ]


@pytest.mark.usefixtures("model_db")
def test_so_far_counts_every_award_and_names_the_timing_trap(client: TestClient) -> None:
    body = client.get(f"{BASE}/by-cohort").json()

    assert body["meta"]["source"] == "synthetic"
    assert _rates(body) == [
        ("2021-22", "Associate degree", "ok", 20, 40, 50.0),
        ("2021-22", "Certificate", "ok", 22, 40, 55.0),
        ("2022-23", "Associate degree", "ok", 10, 50, 20.0),
        ("2022-23", "Certificate", "ok", 19, 50, 38.0),
        ("2023-24", "Associate degree", "ok", 2, 20, 10.0),
        ("2023-24", "Certificate", "ok", 3, 20, 15.0),
    ]
    assert [r["full_years_seen"] for r in body["rows"]] == [3, 3, 2, 2, 1, 1]
    for row in body["rows"]:
        assert row["ci_low"] < row["rate"] < row["ci_high"]
    assert body["meta"]["takeaway"] == (
        "Counted with no time limit, associates fall from 50.0% to 10.0% from the 2021-22 cohort "
        "to 2023-24, "
        "and certificates rise from 52.4% to 60.0% of credentials earned. The 2023-24 cohort has "
        "had 1 year in "
        "full. An associate takes two or more years, so this view mixes time with trend: pick a "
        "fixed number of "
        "years to compare fairly."
    )


@pytest.mark.usefixtures("model_db")
def test_a_fixed_window_leaves_out_cohorts_that_have_not_had_it(client: TestClient) -> None:
    body = client.get(f"{BASE}/by-cohort", params={"window": "2"}).json()

    assert _rates(body) == [
        ("2021-22", "Associate degree", "ok", 10, 40, 25.0),
        ("2021-22", "Certificate", "ok", 12, 40, 30.0),
        ("2022-23", "Associate degree", "ok", 10, 50, 20.0),
        ("2022-23", "Certificate", "ok", 19, 50, 38.0),
        ("2023-24", "Associate degree", "too_new", None, 20, None),
        ("2023-24", "Certificate", "too_new", None, 20, None),
    ]
    assert body["meta"]["takeaway"] == (
        "Within 2 years, counting only cohorts that have had them. "
        "Associates: 25.0% (2021-22) to 20.0% (2022-23), no clear change. "
        "Certificates: 30.0% (2021-22) to 38.0% (2022-23), no clear change."
    )


@pytest.mark.usefixtures("model_db")
def test_a_window_only_one_cohort_has_had_says_there_is_no_trend(client: TestClient) -> None:
    body = client.get(f"{BASE}/by-cohort", params={"window": "3"}).json()

    assert [r["status"] for r in body["rows"]] == [
        "ok",
        "ok",
        "too_new",
        "too_new",
        "too_new",
        "too_new",
    ]
    assert (
        body["meta"]["takeaway"]
        == "Only 1 cohort has had 3 years in full, so there's no trend to compare yet."
    )


@pytest.mark.usefixtures("model_db")
def test_by_program_names_the_program_that_moved_and_hides_small_groups(client: TestClient) -> None:
    body = client.get(
        f"{BASE}/by-program", params={"credential": "certificate", "window": "1"}
    ).json()

    programs = ["51.0801 Health", "52.0411 Business", "52.0201 Business", OTHER]
    assert [(r["cohort"], r["program"], r["earned"], r["cohort_earned"]) for r in body["rows"]] == [
        *zip(["2021-22"] * 4, programs, [None, 12, None, None], [12] * 4, strict=True),
        *zip(["2022-23"] * 4, programs, [15, None, None, None], [19] * 4, strict=True),
        *zip(["2023-24"] * 4, programs, [None] * 4, [None] * 4, strict=True),
    ]
    assert body["meta"]["takeaway"] == (
        "Program 52.0411 Business changed the most: 12 students in the 2021-22 cohort earned a "
        "certificate within "
        "1 year, and fewer than 10 in 2023-24. One program opening, closing or growing can look "
        "like a "
        "college-wide trend."
    )


@pytest.mark.usefixtures("model_db")
def test_drivers_compare_each_group_with_everyone_else_who_came_for_it(client: TestClient) -> None:
    body = client.get(
        f"{BASE}/drivers",
        params={"credential": "associate", "window": "2", "factor": "gateway_math"},
    ).json()

    assert body["everyone_rate"] == 31.7
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
        ("Finished gateway math", "ok", 16, 26, 61.5, 10.8, 50.73, False),
        ("Required, didn't finish", "ok", 4, 37, 10.8, 61.5, -50.73, False),
    ]
    assert body["meta"]["takeaway"] == (
        'Among associate-seekers in the 2021-22 + 2022-23 cohorts, the "Finished gateway math" '
        "group earned an "
        "associate degree within 2 years 61.5% of the time, against 10.8% for everyone else (+50.7 "
        "points)."
    )


@pytest.mark.usefixtures("model_db")
def test_drivers_by_age_join_students_and_say_when_no_gap_is_clear(client: TestClient) -> None:
    body = client.get(
        f"{BASE}/drivers", params={"credential": "certificate", "window": "1", "factor": "age"}
    ).json()

    assert [(r["group"], r["n"], r["rate"], r["likely_noise"]) for r in body["rows"]] == [
        ("20 and younger", 12, 100.0, True),
        ("Older than 24", 18, 100.0, True),
    ]
    assert body["meta"]["takeaway"] == (
        "Among certificate-seekers, no age at entry group differs from everyone else by more than "
        "chance would explain."
    )


@pytest.mark.usefixtures("model_db")
def test_pathways_split_earners_by_goal_without_giving_small_counts_away(
    client: TestClient,
) -> None:
    body = client.get(f"{BASE}/pathways", params={"window": "2"}).json()

    assert [
        (r["sought"], r["pathway"], r["n"], r["share"], r["sought_total"]) for r in body["rows"]
    ] == [
        ("Associate-seekers", "Certificate only", None, None, 20),
        ("Associate-seekers", "Associate only", 16, 80.0, 20),
        ("Associate-seekers", "Both, same year", None, None, 20),
        ("Associate-seekers", "Both, different years", None, None, 20),
        ("Certificate-seekers", "Certificate only", 27, 100.0, 27),
        ("Certificate-seekers", "Associate only", None, None, 27),
        ("Certificate-seekers", "Both, same year", None, None, 27),
        ("Certificate-seekers", "Both, different years", None, None, 27),
    ]
    assert body["meta"]["takeaway"] == (
        "Of the 20 students who came for an associate and earned a credential within 2 years, "
        "fewer than 10 earned "
        "a certificate alongside the associate and fewer than 10 earned a certificate instead of "
        "it."
    )


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/by-cohort", {"window": "4"}),
        ("/by-program", {"window": "so_far"}),
        ("/drivers", {"factor": "student_id"}),
        ("/pathways", {"window": "0"}),
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

    response = client.get(f"{BASE}/by-cohort")

    assert response.status_code == 503
    assert "Load it from the Sandbox pipeline page" in response.text
