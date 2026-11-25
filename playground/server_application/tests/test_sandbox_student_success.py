"""Known-answer tests for the student success snapshot, with the counts planted."""

import pytest
from fastapi.testclient import TestClient

from app.sandbox.student_success import results

KPIS = "/api/v1/sandbox/student-success/kpis"

COUNTS = {
    "2022-23": {
        "entering_students": (200, 200),
        "retention": (100, 200),
        "fall_to_spring": (60, 100),
        "transfer_out": (20, 200),
        "completion": (40, 200),
    },
    "2023-24": {
        "entering_students": (210, 210),
        "retention": (126, 210),
        "fall_to_spring": (60, 100),
        "transfer_out": (5, 210),
        "completion": (21, 210),
    },
}


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the database reads for fixed counts; both cohorts have had all completion years."""
    monkeypatch.setattr(results, "_all_counts", lambda years: COUNTS[years[0]])
    monkeypatch.setattr(results, "_completion_counts", lambda: ({}, {"2022-23", "2023-24"}))


@pytest.mark.usefixtures("planted")
def test_tiles_come_in_order_with_trends(client: TestClient) -> None:
    """The five tiles, in order, each compared with the cohort before."""
    body = client.get(KPIS, params={"cohort": "2023-24"}).json()
    items = {item["id"]: item for item in body["items"]}

    assert [item["label"] for item in body["items"]] == [
        "Enrollment",
        "Retention",
        "Persistence",
        "Transfer out",
        "Completion",
    ]
    assert items["entering_students"]["value"] == 210
    assert items["retention"]["value"] == 60.0
    assert items["retention"]["trend"]["status"] == "good"
    assert items["fall_to_spring"]["trend"]["direction"] == "flat"
    assert items["transfer_out"]["detail"].startswith("5 of 210")
    assert "Synthetic data, not real students" in body["meta"]["filters"]


def test_completion_not_yet_observable_shows_count_so_far(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cohort short of the full completion window shows its count so far, with no arrow."""
    unobserved = {**COUNTS["2023-24"], "completion": None}
    by_year = {**COUNTS, "2023-24": unobserved}
    monkeypatch.setattr(results, "_all_counts", lambda years: by_year[years[0]])
    monkeypatch.setattr(
        results, "_completion_counts", lambda: ({"2023-24": (42, 210)}, {"2022-23"})
    )
    body = client.get(KPIS, params={"cohort": "2023-24"}).json()
    completion = next(item for item in body["items"] if item["id"] == "completion")

    assert completion["value"] == 20.0
    assert completion["trend"] is None
    assert completion["detail"].startswith("42 of 210")
    assert completion["detail"].endswith("window isn't over yet")


def test_completion_so_far_hidden_under_group_size(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial-window cohort too small to show still gets no completion tile."""
    monkeypatch.setattr(results, "_all_counts", lambda years: COUNTS[years[0]])
    monkeypatch.setattr(results, "_completion_counts", lambda: ({"2023-24": (1, 5)}, set()))
    body = client.get(KPIS, params={"cohort": "2023-24"}).json()

    assert "completion" not in [item["id"] for item in body["items"]]


def test_pooled_completion_counts_only_observed_cohorts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The all-cohorts view pools completion over the cohorts with the full window."""
    monkeypatch.setattr(
        results, "_all_counts", lambda years: {**COUNTS["2023-24"], "completion": None}
    )
    monkeypatch.setattr(results, "_completion_counts", lambda: ({}, {"2021-22", "2022-23"}))
    asked = []
    monkeypatch.setattr(
        results, "_measure_counts", lambda name, years: asked.append(years) or (60, 400)
    )
    body = client.get(KPIS, params={"cohort": "all"}).json()
    completion = next(item for item in body["items"] if item["id"] == "completion")

    assert asked == [["2021-22", "2022-23"]]
    assert completion["value"] == 15.0
    assert completion["trend"] is None
    assert completion["detail"].endswith("(cohorts 2021-22, 2022-23 only)")


def test_a_cohort_short_of_year_2_shows_its_rate_so_far_without_an_arrow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retention and transfer out need year 2, which 2024-25 hasn't fully had.

    Against the finished 2023-24 the share so far would read as a drop, so those two tiles get no
    arrow. Enrollment and persistence don't need year 2 and keep theirs.
    """
    partly_observed = {
        "entering_students": (220, 220),
        "retention": (88, 220),
        "fall_to_spring": (70, 100),
        "transfer_out": (2, 220),
        "completion": None,
    }
    by_year = {**COUNTS, "2024-25": partly_observed}
    monkeypatch.setattr(results, "_all_counts", lambda years: by_year[years[0]])
    monkeypatch.setattr(
        results, "_completion_counts", lambda: ({"2024-25": (2, 220)}, {"2022-23", "2023-24"})
    )
    body = client.get(KPIS, params={"cohort": "2024-25"}).json()
    items = {item["id"]: item for item in body["items"]}

    assert items["retention"]["value"] == 40.0
    for name in ("retention", "transfer_out"):
        assert items[name]["trend"] is None
        assert items[name]["detail"].endswith(
            "; year 2 isn't fully observed yet, so this will likely rise"
        )
    assert items["entering_students"]["trend"]["label"] == "+4.8% vs 2023-24"
    assert items["fall_to_spring"]["trend"]["label"] == "+16.7% vs 2023-24"
    assert "year 2 isn't fully observed" not in items["fall_to_spring"]["detail"]


@pytest.mark.usefixtures("planted")
def test_a_finished_cohort_keeps_its_retention_and_transfer_out_arrows(client: TestClient) -> None:
    body = client.get(KPIS, params={"cohort": "2023-24"}).json()
    items = {item["id"]: item for item in body["items"]}

    for name in ("retention", "transfer_out"):
        assert items[name]["trend"] is not None
        assert "year 2 isn't fully observed" not in items[name]["detail"]
    # The tooltips are the definitions the chat quotes for each card.
    assert body["meta"]["definitions"] == results.kpi_definitions()


def test_the_pooled_lens_is_not_called_short_of_year_2(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pool is 2021-22 to 2023-24, every one of which has had year 2."""
    monkeypatch.setattr(results, "_all_counts", lambda years: COUNTS["2023-24"])
    monkeypatch.setattr(results, "_completion_counts", lambda: ({}, {"2022-23", "2023-24"}))
    body = client.get(KPIS, params={"cohort": "all"}).json()
    items = {item["id"]: item for item in body["items"]}

    assert "year 2 isn't fully observed" not in items["retention"]["detail"]
    assert "year 2 isn't fully observed" not in items["transfer_out"]["detail"]


TRENDS = "/api/v1/sandbox/student-success/trends"


def test_trends_return_every_metric_per_cohort(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five metrics per cohort, rates from counts, small groups hidden, partial cohorts flagged."""
    by_year = {
        "2021-22": COUNTS["2022-23"],
        "2022-23": COUNTS["2022-23"],
        "2023-24": COUNTS["2023-24"],
        "2024-25": {**COUNTS["2023-24"], "completion": (1, 5)},
    }
    monkeypatch.setattr(results, "_all_counts", lambda years: dict(by_year[years[0]]))
    so_far = {"2023-24": (42, 210), "2024-25": (1, 5)}
    monkeypatch.setattr(results, "_completion_counts", lambda: (so_far, {"2021-22", "2022-23"}))

    body = client.get(TRENDS).json()
    rows = {(row["metric"], row["cohort"]): row for row in body["rows"]}

    assert len(body["rows"]) == 20
    assert rows[("retention", "2023-24")]["value"] == 60.0
    assert rows[("retention", "2023-24")]["n"] == 210
    assert rows[("entering_students", "2022-23")]["value"] == 200
    assert rows[("completion", "2024-25")]["value"] is None
    assert rows[("completion", "2023-24")]["partial"] is True
    assert rows[("completion", "2023-24")]["value"] == 20.0
    assert rows[("retention", "2024-25")]["partial"] is True
    assert rows[("retention", "2023-24")]["partial"] is False
    assert body["meta"]["source"] == "synthetic"


EQUITY = "/api/v1/sandbox/student-success/equity"


class _Gap:
    """A stand-in for one gap finder row."""

    def __init__(self, value: str, numerator: int, denominator: int, gap_pts: float) -> None:
        """A one-way group row the equity view reads."""
        self.group_dimensions = ("pell",)
        self.group_values = (value,)
        self.status = "ok"
        self.numerator = numerator
        self.denominator = denominator
        self.gap_pts = gap_pts
        self.likely_noise = False


def test_equity_hides_small_groups_and_names_the_gap(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Group sizes, milestones, programs and the retention takeaway, with small cells hidden.

    Unknown (5) is the only small group, so No Pell, the smaller shown group, is hidden as its
    cover, in the groups and in the program's segments.
    """
    from app.sandbox.student_success import equity

    groups = [["Y", 200, 100, 80, 20], ["N", 100, 60, 50, 15], ["U", 5, 1, 1, 0]]
    programs = [["24.0101", "Y", 60], ["24.0101", "N", 40], ["24.0101", "U", 5]]
    monkeypatch.setattr(
        equity.credentials,
        "_fetch",
        lambda sql, params: programs if "program_of_study" in sql else groups,
    )
    monkeypatch.setattr(
        equity,
        "_retention_gaps",
        lambda dimension, years: {
            "Pell": _Gap("Y", 40, 100, -15.0),
            "No Pell": _Gap("N", 110, 200, 15.0),
        },
    )
    monkeypatch.setattr(equity.results, "_measure_counts", lambda name, years: (150, 305))

    body = client.get(EQUITY, params={"cohort": "2023-24", "dimension": "pell"}).json()
    by_group = {group["group"]: group for group in body["groups"]}

    assert [group["group"] for group in body["groups"]] == ["Pell", "No Pell", "Unknown"]
    assert by_group["Pell"]["milestones"] == [50.0, 40.0, 10.0]
    assert by_group["Pell"]["retention_gap_pts"] == -15.0
    assert by_group["Unknown"]["n"] is None
    assert by_group["Unknown"]["milestones"] == [None, None, None]
    assert by_group["No Pell"]["n"] is None
    assert by_group["No Pell"]["retention_gap_pts"] is None
    assert body["everyone"]["retention"] == 49.2
    assert body["meta"]["takeaway"].startswith("Pell students retain 15.0 points below")
    segments = {cell["group"]: cell["n"] for cell in body["programs"][0]["segments"]}
    assert segments == {"Pell": 60, "No Pell": None, "Unknown": None}


def test_equity_first_gen_has_no_retention_gaps(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First generation skips the gap finder until the data quality finding is settled."""
    from app.sandbox.student_success import equity

    monkeypatch.setattr(
        equity.credentials,
        "_fetch",
        lambda sql, params: [] if "program_of_study" in sql else [["Y", 50, 20, 10, 2]],
    )
    monkeypatch.setattr(equity.results, "_measure_counts", lambda name, years: (25, 50))

    body = client.get(EQUITY, params={"cohort": "2023-24", "dimension": "first_gen"}).json()

    assert body["groups"][0]["retention_gap_pts"] is None
    assert "data quality finding" in body["meta"]["takeaway"]


ACTIONS = "/api/v1/sandbox/student-success/actions"


def _plant_action_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plant rows for each of the board's three queries and a fixed DFW grade table."""
    from app.sandbox.student_success import actions

    # Group, students, stopped out, near 15, near 6, gateway, priority, MVSU priority.
    flags = [["Y", 100, 20, 15, 8, 40, 12, 11], ["N", 200, 30, 5, 2, 60, 18, 4]]
    grades = [["M", "MATH 101", "F", 20], ["M", "MATH 101", "4", 20], ["E", "ENGL 101", "W", 3]]

    def fake_fetch(sql: str, params: list[str] | None = None) -> list[list]:
        """Planted rows for each of the board's three queries."""
        if "LIMIT 1" in sql:
            return [["2025-26"]]
        if "math_or_english_gateway, ce.course_name" in sql:
            return grades
        return flags

    monkeypatch.setattr(actions.credentials, "_fetch", fake_fetch)
    monkeypatch.setattr(actions, "_dfw_outcomes", lambda: {"F": True, "W": True, "4": False})


def test_mvsu_actions_drop_the_associate_tile(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MVSU's board has no associate tile, a next-term gateway step and its own priority count."""
    _plant_action_rows(monkeypatch)

    params = {"cohort": "2023-24", "dimension": "pell", "school": "mvsu"}
    body = client.get(ACTIONS, params=params).json()
    tiles = {tile["id"]: tile for tile in body["tiles"]}
    groups = {group["group"]: group for group in body["groups"]}

    assert list(tiles) == ["stopped_out", "gateway", "priority"]
    assert tiles["gateway"]["action"] == (
        "Recommend enrolling in the gateway course the next semester or the next summer term."
    )
    assert tiles["priority"]["value"] == 15
    assert groups["No Pell"]["priority"] is None
    assert "Approaching an associate" not in body["meta"]["definitions"]


def test_actions_count_each_group_and_hide_small_ones(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tiles add up the groups, small counts are hidden, and gateway courses rank by DFW."""
    _plant_action_rows(monkeypatch)

    body = client.get(ACTIONS, params={"cohort": "2023-24", "dimension": "pell"}).json()
    tiles = {tile["id"]: tile for tile in body["tiles"]}
    groups = {group["group"]: group for group in body["groups"]}

    assert tiles["stopped_out"]["value"] == 50
    assert tiles["near_15"]["value"] == 20
    assert "(10 within 6)" in tiles["near_15"]["detail"]
    assert tiles["gateway"]["share"] == 33.3
    assert groups["No Pell"]["near_15"] is None
    assert body["gateway_courses"] == [
        {"course": "MATH 101", "subject": "Math", "dfw_rate": 50.0, "n": 40}
    ]
    assert body["meta"]["takeaway"].startswith("The largest group to act on is gateway")


def test_action_trends_are_red_or_green_never_gray() -> None:
    """A rise in share is red; a fall or no change is green, for every tile."""
    from app.sandbox.student_success import actions

    rose = actions._trend(12.5, 10.0, "2022-23")
    fell = actions._trend(4.0, 6.0, "2022-23")
    same = actions._trend(6.0, 6.0, "2022-23")

    assert rose is not None and (rose.status, rose.label) == ("bad", "+2.5 pts vs 2022-23")
    assert fell is not None and (fell.status, fell.direction) == ("good", "down")
    assert same is not None and (same.status, same.direction) == ("good", "flat")
    assert actions._trend(None, 35.0, "2022-23") is None


ACTION_EXPORT = "/api/v1/sandbox/student-success/actions/students.csv"


def test_action_export_flags_each_student_by_the_boards_rules(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Priority is two or more groups on the college's board, and both of two on MVSU's."""
    import csv
    import io

    from app.sandbox.student_success import action_export, actions

    # Student, cohort, stopped out, near 15, gateway.
    students = [
        ["s1", "2023-24", 1, 0, 1],  # stopped and gateway: priority on both boards
        ["s2", "2023-24", 1, 1, 0],  # stopped and near done: priority on the college's only
        ["s3", "2023-24", 0, 0, 1],  # gateway only
        ["s4", "2023-24", 0, 0, 0],  # in no group
    ]
    monkeypatch.setattr(actions.credentials, "_fetch", lambda sql, params=None: [["2025-26"]])
    monkeypatch.setattr(action_export, "_fetch", lambda sql, params: students)

    def rows(**params: str) -> list[dict[str, str]]:
        response = client.get(ACTION_EXPORT, params={"cohort": "2023-24", **params})
        assert response.status_code == 200
        return list(csv.DictReader(io.StringIO(response.text)))

    college = rows()
    assert [row["Outreach_Priority"] for row in college] == ["Yes", "Yes", "No", "No"]
    assert list(college[0]) == [
        "Student_GUID",
        "Cohort",
        "Stopped_Out_After_Fall",
        "Approaching_Associate",
        "Gateway_Course_Barrier",
        "Outreach_Priority",
    ]
    mvsu = rows(school="mvsu")
    assert "Approaching_Associate" not in mvsu[0]
    assert [row["Outreach_Priority"] for row in mvsu] == ["Yes", "No", "No", "No"]
    assert [row["Student_GUID"] for row in rows(tile="gateway")] == ["s1", "s3"]
    assert [row["Student_GUID"] for row in rows(tile="priority", school="mvsu")] == ["s1"]
