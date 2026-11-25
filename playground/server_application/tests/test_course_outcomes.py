from collections.abc import Callable
from pathlib import Path
from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.sandbox.course_outcomes.results import who
from app.sandbox.course_outcomes.schemas import GenderChoice, RaceChoice
from tests.published_results import PAGES_MANIFEST, row

DFW = "/api/v1/sandbox/course-outcomes/dfw"
QUERY = "/api/v1/sandbox/results/query"
GROUP = "course x gender x race"
BLACK = "Black or African American"
BLACK_MEN = "M x Black or African American"
EVERYONE = {"race": "all", "gender": "all"}

# Three courses: one where Black men are shown, one where they're hidden, one too small. Then
# Black students of either gender, and each gender of any race, for the "all" choices.
DFW_ROWS = [
    row("all", "all", 0.3, 30000, "dfw_rate"),
    row("course", "COM 101", 0.3851, 483, "dfw_rate"),
    row("course", "ENG 102", 0.2584, 1130, "dfw_rate"),
    row("course", "ART 100", 0.2, 50, "dfw_rate"),
    row(GROUP, f"COM 101 x {BLACK_MEN}", 0.7143, 28, "dfw_rate"),
    row(GROUP, f"ENG 102 x {BLACK_MEN}", None, None, "dfw_rate"),
    row(GROUP, "COM 101 x F x Black or African American", 0.4, 30, "dfw_rate"),
    row("course x race", f"COM 101 x {BLACK}", 0.6, 70, "dfw_rate"),
    row("course x race", f"ENG 102 x {BLACK}", 0.3, 150, "dfw_rate"),
    row("course x gender", "COM 101 x F", 0.35, 250, "dfw_rate"),
    row("course x gender", "ENG 102 x F", 0.2, 600, "dfw_rate"),
    row("course x gender", "ART 100 x F", None, None, "dfw_rate"),
    row("course x gender", "COM 101 x M", 0.42, 233, "dfw_rate"),
    row("course x gender", "ENG 102 x M", 0.31, 530, "dfw_rate"),
]


@pytest.fixture
def results_file(publish_results: Callable[..., Path]) -> Path:
    """The DFW rows, published."""
    return publish_results(PAGES_MANIFEST, DFW_ROWS)


def test_lines_up_the_group_with_everyone_in_each_course(
    client: TestClient, results_file: Path
) -> None:
    body = client.get(DFW).json()

    assert body["courses_considered"] == 2  # ART 100 is under 200 enrollments
    assert body["courses_with_group_hidden"] == 1
    first = body["rows"][0]
    assert first["course"] == "COM 101"
    assert first["everyone"] == {"rate": 38.5, "n": 483}
    assert first["group"] == {"rate": 71.4, "n": 28}
    assert first["difference_pts"] == 32.9


def test_a_hidden_group_stays_blank(client: TestClient, results_file: Path) -> None:
    rows = {row["course"]: row for row in client.get(DFW).json()["rows"]}

    assert rows["ENG 102"]["group"] == {"rate": None, "n": None}
    assert rows["ENG 102"]["difference_pts"] is None


def test_busiest_sort_and_minimum(client: TestClient, results_file: Path) -> None:
    body = client.get(DFW, params={"sort": "busiest", "min_enrollments": 10}).json()

    assert [row["course"] for row in body["rows"]] == ["ENG 102", "COM 101", "ART 100"]


def test_dfw_specs_replay_through_the_builder(client: TestClient, results_file: Path) -> None:
    body = client.get(DFW).json()
    everyone_spec, group_spec = body["meta"]["specs"]

    assert everyone_spec["group_by"] == ["course"]
    assert everyone_spec["min_denominator"] == body["min_enrollments"]
    assert group_spec["where"] == {"gender": "M", "race": "Black or African American"}
    everyone = client.post(QUERY, json=everyone_spec).json()["rows"]
    group = client.post(QUERY, json=group_spec).json()["rows"]
    assert sorted(r["group"]["course"] for r in everyone) == sorted(
        r["course"] for r in body["rows"]
    )
    # The hidden ENG 102 group drops out under the spec's size floor; the page shows it blank.
    assert [(r["group"]["course"], r["denominator"]) for r in group] == [("COM 101", 28)]


@pytest.mark.parametrize(
    ("race", "gender", "label"),
    [
        (BLACK, "M", "Black or African American men"),
        ("Asian", "F", "Asian women"),
        (BLACK, "all", "Black or African American students"),
        ("all", "M", "Men"),
        ("all", "F", "Women"),
        ("all", "all", "Everyone"),
    ],
)
def test_who_names_the_group(race: str, gender: str, label: str) -> None:
    assert who(race, gender) == label


def test_the_pickers_offer_all_beside_each_race_and_gender() -> None:
    assert get_args(RaceChoice)[-1] == "all"
    assert len(get_args(RaceChoice)) == 9
    assert get_args(GenderChoice) == ("M", "F", "all")


@pytest.mark.parametrize(
    ("params", "group", "group_by", "where"),
    [
        (
            {},
            "Black or African American men",
            ["course", "gender", "race"],
            {"gender": "M", "race": BLACK},
        ),
        (
            {"gender": "all"},
            "Black or African American students",
            ["course", "race"],
            {"race": BLACK},
        ),
        ({"race": "all"}, "Men", ["course", "gender"], {"gender": "M"}),
        ({"race": "all", "gender": "F"}, "Women", ["course", "gender"], {"gender": "F"}),
    ],
)
def test_each_group_reads_its_own_course_breakdown(
    client: TestClient,
    results_file: Path,
    params: dict[str, str],
    group: str,
    group_by: list[str],
    where: dict[str, str],
) -> None:
    response = client.get(DFW, params=params)

    assert response.status_code == 200
    body = response.json()
    everyone_spec, group_spec = body["meta"]["specs"]
    assert everyone_spec["group_by"] == ["course"]
    assert (group_spec["group_by"], group_spec["where"]) == (group_by, where)
    assert group_spec["min_denominator"] == 10
    assert body["group_label"] == group
    assert body["meta"]["title"] == f"DFW rate by course: {group} against everyone in the course"
    assert f"Group: {group}" in body["meta"]["filters"]
    assert body["meta"]["fields_used"] == [
        f"success_measures: dfw_rate by course and {' x '.join(group_by)}"
    ]
    assert client.post(QUERY, json=group_spec).status_code == 200


def test_one_race_of_either_gender_lines_up_with_everyone(
    client: TestClient, results_file: Path
) -> None:
    body = client.get(DFW, params={"gender": "all"}).json()

    assert (body["race"], body["gender"]) == (BLACK, "all")
    assert [(row["course"], row["group"], row["difference_pts"]) for row in body["rows"]] == [
        ("COM 101", {"rate": 60.0, "n": 70}, 21.5),
        ("ENG 102", {"rate": 30.0, "n": 150}, 4.2),
    ]


def test_one_gender_of_any_race_keeps_a_hidden_course_blank(
    client: TestClient, results_file: Path
) -> None:
    body = client.get(DFW, params={"race": "all", "gender": "F", "min_enrollments": 10}).json()

    assert body["courses_with_group_hidden"] == 1
    assert [(row["course"], row["difference_pts"]) for row in body["rows"]] == [
        ("COM 101", -3.5),
        ("ENG 102", -5.8),
        ("ART 100", None),
    ]


def test_everyone_is_the_group_with_no_difference(client: TestClient, results_file: Path) -> None:
    body = client.get(DFW, params={**EVERYONE, "min_enrollments": 10}).json()

    assert (body["race"], body["gender"]) == ("all", "all")
    assert [spec["group_by"] for spec in body["meta"]["specs"]] == [["course"]]
    assert body["courses_considered"] == 3
    assert body["courses_with_group_hidden"] == 0
    for course in body["rows"]:
        assert course["group"] == course["everyone"]
        assert course["difference_pts"] is None
    assert body["group_label"] == "Everyone"
    assert body["meta"]["title"] == "DFW rate by course: Everyone"
    assert "Group: Everyone" in body["meta"]["filters"]
    assert body["meta"]["fields_used"] == ["success_measures: dfw_rate by course"]


@pytest.mark.parametrize("sort", ["difference", "group_dfw"])
def test_everyone_sorts_a_difference_by_everyones_dfw(
    client: TestClient, results_file: Path, sort: str
) -> None:
    # The builder answers in course order (ART 100 first), so this is the page's own sort.
    body = client.get(DFW, params={**EVERYONE, "min_enrollments": 10, "sort": sort}).json()

    assert [row["course"] for row in body["rows"]] == ["COM 101", "ENG 102", "ART 100"]
    assert body["meta"]["filters"][-1] == "Sorted by: highest DFW"


def test_everyone_still_sorts_busiest_first(client: TestClient, results_file: Path) -> None:
    params = {**EVERYONE, "min_enrollments": 10, "sort": "busiest"}
    body = client.get(DFW, params=params).json()

    assert [row["course"] for row in body["rows"]] == ["ENG 102", "COM 101", "ART 100"]
    assert body["meta"]["filters"][-1] == "Sorted by: busiest"


@pytest.mark.parametrize(
    ("sort", "words"), [("difference", "difference"), ("group_dfw", "group dfw")]
)
def test_a_group_keeps_its_sort_words(
    client: TestClient, results_file: Path, sort: str, words: str
) -> None:
    body = client.get(DFW, params={"gender": "all", "sort": sort}).json()

    assert body["meta"]["filters"][-1] == f"Sorted by: {words}"


MIDTERMS = "/api/v1/sandbox/course-outcomes/midterm-alerts"
ALERT = "midterm_alert_rate"
RECOVERY = "midterm_recovery_rate"

# Planted midterm rows: three courses, the group shown in two, recovery hidden.
MIDTERM_ROWS = [
    row("all", "all", 0.246, 80000, ALERT),
    row("gender x race", BLACK_MEN, 0.355, 2400, ALERT),
    row("gender x race", "F x Black or African American", 0.3, 3000, ALERT),
    row("course", "COM 101", 0.25, 400, ALERT),
    row("course", "ENG 102", 0.2, 1000, ALERT),
    row("course", "MAT 108", 0.3, 600, ALERT),
    row(GROUP, f"COM 101 x {BLACK_MEN}", 0.3, 40, ALERT),
    row(GROUP, f"ENG 102 x {BLACK_MEN}", 0.5, 60, ALERT),
    row(GROUP, f"MAT 108 x {BLACK_MEN}", None, None, ALERT),
    row("all", "all", 0.269, 19000, RECOVERY),
    row("gender x race", BLACK_MEN, None, None, RECOVERY),
    row("gender x race", "F x Black or African American", None, None, RECOVERY),
    row("race", BLACK, 0.34, 5400, ALERT),
    row("gender", "F", 0.22, 40000, ALERT),
    row("race", BLACK, 0.31, 1800, RECOVERY),
    row("gender", "F", 0.28, 4000, RECOVERY),
    row("course x race", f"COM 101 x {BLACK}", 0.32, 90, ALERT),
    row("course x race", f"ENG 102 x {BLACK}", 0.45, 130, ALERT),
    row("course x race", f"MAT 108 x {BLACK}", 0.4, 80, ALERT),
    row("course x gender", "COM 101 x F", 0.24, 200, ALERT),
    row("course x gender", "ENG 102 x F", 0.18, 500, ALERT),
    row("course x gender", "MAT 108 x F", 0.31, 300, ALERT),
]


@pytest.fixture
def midterm_file(publish_results: Callable[..., Path]) -> Path:
    """The DFW rows and the planted midterm rows, published together."""
    return publish_results(PAGES_MANIFEST, DFW_ROWS + MIDTERM_ROWS)


def test_midterm_alerts_line_up_the_group_widest_difference_first(
    client: TestClient, midterm_file: Path
) -> None:
    body = client.get(MIDTERMS).json()

    assert body["group_label"] == "Black or African American men"
    assert body["courses_considered"] == 3
    assert body["courses_with_group_hidden"] == 1
    assert [row["course"] for row in body["rows"]] == ["ENG 102", "COM 101", "MAT 108"]
    assert body["rows"][0]["difference_pts"] == 30.0
    assert body["rows"][2]["group"] == {"rate": None, "n": None}
    assert body["alert"] == {
        "group": {"rate": 35.5, "n": 2400},
        "everyone": {"rate": 24.6, "n": 80000},
        "difference_pts": 10.9,
    }


def test_a_hidden_recovery_rate_stays_blank(client: TestClient, midterm_file: Path) -> None:
    recovery = client.get(MIDTERMS).json()["recovery"]

    assert recovery["group"] == {"rate": None, "n": None}
    assert recovery["everyone"] == {"rate": 26.9, "n": 19000}
    assert recovery["difference_pts"] is None


def test_midterm_minimum_and_other_group(client: TestClient, midterm_file: Path) -> None:
    # Black women have no course rows at all, as on the deploy's trimmed copy when a group is
    # hidden in every course: each course reads as hidden, not as an error.
    body = client.get(MIDTERMS, params={"gender": "F", "min_enrollments": 500}).json()

    assert body["courses_considered"] == 2  # COM 101 has 400
    assert body["courses_with_group_hidden"] == 2
    assert body["alert"]["group"] == {"rate": 30.0, "n": 3000}


def test_midterm_alerts_are_labelled_planted(client: TestClient, midterm_file: Path) -> None:
    meta = client.get(MIDTERMS).json()["meta"]

    assert meta["source"] == "synthetic"
    assert "circular by construction" in meta["definitions"]["Planted effect"]
    assert "whether alerts work" in meta["definitions"]["Planted effect"]
    assert "Not tested" in meta["definitions"]["Difference"]


def test_midterm_specs_name_every_read(client: TestClient, midterm_file: Path) -> None:
    body = client.get(MIDTERMS).json()
    specs = body["meta"]["specs"]

    assert [(spec["measure"], spec["group_by"]) for spec in specs] == [
        (ALERT, ["gender", "race"]),
        (RECOVERY, ["gender", "race"]),
        (ALERT, ["course"]),
        (ALERT, ["course", "gender", "race"]),
    ]
    alert = client.post(QUERY, json=specs[0]).json()
    assert [(r["metric_rate"], r["denominator"]) for r in alert["rows"]] == [(0.355, 2400)]
    assert alert["everyone"]["denominator"] == body["alert"]["everyone"]["n"]


@pytest.mark.parametrize(
    ("params", "group", "cards", "table", "where", "alert", "recovery", "order"),
    [
        (
            {"gender": "all"},
            "Black or African American students",
            ["race"],
            ["course", "race"],
            {"race": BLACK},
            ({"rate": 34.0, "n": 5400}, 9.4),
            ({"rate": 31.0, "n": 1800}, 4.1),
            ["ENG 102", "MAT 108", "COM 101"],
        ),
        (
            {"race": "all", "gender": "F"},
            "Women",
            ["gender"],
            ["course", "gender"],
            {"gender": "F"},
            ({"rate": 22.0, "n": 40000}, -2.6),
            ({"rate": 28.0, "n": 4000}, 1.1),
            ["MAT 108", "COM 101", "ENG 102"],
        ),
    ],
)
def test_midterms_for_one_race_or_one_gender(
    client: TestClient,
    midterm_file: Path,
    params: dict[str, str],
    group: str,
    cards: list[str],
    table: list[str],
    where: dict[str, str],
    alert: tuple[dict, float],
    recovery: tuple[dict, float],
    order: list[str],
) -> None:
    response = client.get(MIDTERMS, params=params)

    assert response.status_code == 200
    body = response.json()
    assert [(s["measure"], s["group_by"], s["where"]) for s in body["meta"]["specs"]] == [
        (ALERT, cards, where),
        (RECOVERY, cards, where),
        (ALERT, ["course"], {}),
        (ALERT, table, where),
    ]
    assert (body["alert"]["group"], body["alert"]["difference_pts"]) == alert
    assert (body["recovery"]["group"], body["recovery"]["difference_pts"]) == recovery
    assert [row["course"] for row in body["rows"]] == order
    assert body["group_label"] == group
    assert body["meta"]["title"] == (
        f"Midterm alerts by course: {group} against everyone in the course"
    )
    assert f"Group: {group}" in body["meta"]["filters"]


def test_everyone_midterms_read_the_everyone_rows(client: TestClient, midterm_file: Path) -> None:
    body = client.get(MIDTERMS, params=EVERYONE).json()

    everyone_alert = {"rate": 24.6, "n": 80000}
    assert body["alert"] == {
        "group": everyone_alert,
        "everyone": everyone_alert,
        "difference_pts": None,
    }
    assert body["recovery"]["group"] == body["recovery"]["everyone"] == {"rate": 26.9, "n": 19000}
    assert body["recovery"]["difference_pts"] is None
    assert [(s["measure"], s["group_by"], s["where"]) for s in body["meta"]["specs"]] == [
        (ALERT, ["gender", "race"], {}),
        (RECOVERY, ["gender", "race"], {}),
        (ALERT, ["course"], {}),
    ]
    assert body["courses_with_group_hidden"] == 0
    # Sorted by everyone's alert rate, not the builder's course order.
    assert [row["course"] for row in body["rows"]] == ["MAT 108", "COM 101", "ENG 102"]
    assert all(row["difference_pts"] is None for row in body["rows"])
    assert body["group_label"] == "Everyone"
    assert body["meta"]["title"] == "Midterm alerts by course: Everyone"
    assert body["meta"]["filters"][0] == "Group: Everyone"
    assert body["meta"]["filters"][-1] == "Sorted by: alert rate"


@pytest.mark.parametrize("path", [DFW, MIDTERMS])
@pytest.mark.parametrize(
    "params", [{"race": "Martian"}, {"gender": "X"}, {"race": "All"}, {"gender": "ALL"}]
)
def test_an_unknown_race_or_gender_is_refused(
    client: TestClient, midterm_file: Path, path: str, params: dict[str, str]
) -> None:
    assert client.get(path, params=params).status_code == 422


@pytest.mark.parametrize("path", [DFW, MIDTERMS])
def test_all_is_accepted_for_both_pickers(
    client: TestClient, midterm_file: Path, path: str
) -> None:
    assert client.get(path, params=EVERYONE).status_code == 200


def test_dfw_ignores_the_midterm_rows(client: TestClient, midterm_file: Path) -> None:
    body = client.get(DFW).json()

    assert body["courses_considered"] == 2
    assert [row["course"] for row in body["rows"]] == ["COM 101", "ENG 102"]


def test_unpublished_midterms_are_unavailable(client: TestClient, results_file: Path) -> None:
    response = client.get(MIDTERMS)

    assert response.status_code == 503
    assert "midterm_alert_rate" in response.json()["error"]["message"]


def test_a_refused_spec_is_a_server_problem(
    client: TestClient, publish_results: Callable[..., Path]
) -> None:
    # A manifest without dfw_rate by course refuses the page's own spec: a 503, never a 400.
    publish_results(PAGES_MANIFEST.replace("    - [course]\n", "", 1), DFW_ROWS)

    response = client.get(DFW)

    assert response.status_code == 503
    assert "dfw_rate by course isn't approved" in response.json()["error"]["message"]
