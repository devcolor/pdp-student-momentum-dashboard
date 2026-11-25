from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.published_results import PAGES_MANIFEST, gap, row

OUTCOMES = "/api/v1/sandbox/deaggregation/outcomes"
QUERY = "/api/v1/sandbox/results/query"
PAIR = "gender x race"
BLACK_MEN = "M x Black or African American"
BLACK_WOMEN = "F x Black or African American"

# Every measure the page reads needs its everyone row. The ones the tests don't look at closely
# have the group hidden.
ROWS = [
    row("all", "all", 0.2785, 3282),
    row(PAIR, BLACK_MEN, 0.1474, 190),
    row(PAIR, BLACK_WOMEN, 0.2026, 306),
    row("all", "all", 0.30, 30000, "dfw_rate"),
    row(PAIR, BLACK_MEN, 0.376, 3285, "dfw_rate"),
    row("all", "all", 0.55, 3282, "retention"),
    row(PAIR, BLACK_MEN, None, None, "retention"),
    row("all", "all", 0.7512, 3282, "first_fall_good_standing"),
    row(PAIR, BLACK_MEN, 0.6316, 190, "first_fall_good_standing"),
    row(PAIR, BLACK_WOMEN, 0.7255, 306, "first_fall_good_standing"),
    row("all", "all", 0.8104, 3282, "fall_to_spring_retention"),
    row(PAIR, BLACK_MEN, 0.7947, 190, "fall_to_spring_retention"),
    row(PAIR, BLACK_WOMEN, 0.8268, 306, "fall_to_spring_retention"),
    *(
        line
        for measure in ("gateway_english", "credit_completion", "persistence")
        for line in (
            row("all", "all", 0.5, 3282, measure),
            row(PAIR, BLACK_MEN, None, None, measure),
        )
    ),
]
GAPS = [
    gap(PAIR, BLACK_MEN, -13.92, -26),
    gap(PAIR, BLACK_WOMEN, -8.37, -25),
    gap(PAIR, BLACK_MEN, -12.18, -23, measure="first_fall_good_standing"),
    gap(PAIR, BLACK_WOMEN, -2.71, -8, likely_noise=True, measure="first_fall_good_standing"),
    gap(PAIR, BLACK_MEN, -1.6, -3, likely_noise=True, measure="fall_to_spring_retention"),
    # A hidden group's gap isn't compared, so the page shows none and ranks it nowhere.
    gap(PAIR, BLACK_MEN, None, None, measure="retention", status="suppressed"),
]


@pytest.fixture
def results_file(publish_results: Callable[..., Path]) -> Path:
    """A small published results file with every measure the page reads."""
    return publish_results(PAGES_MANIFEST, ROWS, GAPS)


def by_measure(body: dict) -> dict:
    """The response's rows keyed by measure."""
    return {row["measure"]: row for row in body["rows"]}


def test_reads_rates_and_gaps_for_the_group(client: TestClient, results_file: Path) -> None:
    response = client.get(OUTCOMES)

    assert response.status_code == 200
    math = by_measure(response.json())["gateway_math"]
    assert math["group"] == {"rate": 14.7, "n": 190}
    assert math["other_gender"] == {"rate": 20.3, "n": 306}
    assert math["everyone"] == {"rate": 27.9, "n": 3282}
    gap = (math["gap_pts"], math["likely_noise"], math["rank"], math["ranked_of"])
    assert gap == (-13.92, False, 1, 2)


def test_term_measures_follow_gateway_english(client: TestClient, results_file: Path) -> None:
    measures = [row["measure"] for row in client.get(OUTCOMES).json()["rows"]]

    english = measures.index("gateway_english")
    after = measures[english + 1 : english + 3]
    assert after == ["first_fall_good_standing", "fall_to_spring_retention"]


def test_term_measures_read_rates_and_gaps(client: TestClient, results_file: Path) -> None:
    rows = by_measure(client.get(OUTCOMES).json())

    standing = rows["first_fall_good_standing"]
    assert standing["label"] == "Good standing after first fall"
    assert (standing["counts"], standing["lower_is_better"]) == ("students", False)
    assert standing["group"] == {"rate": 63.2, "n": 190}
    assert standing["other_gender"] == {"rate": 72.5, "n": 306}
    assert standing["everyone"] == {"rate": 75.1, "n": 3282}
    gap = (standing["gap_pts"], standing["likely_noise"], standing["rank"], standing["ranked_of"])
    assert gap == (-12.18, False, 1, 2)
    assert standing["not_tested"] is None

    retention = rows["fall_to_spring_retention"]
    assert retention["label"] == "Fall-to-spring retention"
    assert retention["group"] == {"rate": 79.5, "n": 190}
    gap = (
        retention["gap_pts"],
        retention["likely_noise"],
        retention["rank"],
        retention["ranked_of"],
    )
    assert gap == (-1.6, True, 1, 1)
    assert retention["not_tested"] is None


def test_untested_and_hidden_measures_say_why(client: TestClient, results_file: Path) -> None:
    rows = by_measure(client.get(OUTCOMES).json())

    assert rows["dfw_rate"]["lower_is_better"] is True
    assert rows["dfw_rate"]["gap_pts"] is None
    assert rows["dfw_rate"]["not_tested"]
    assert rows["retention"]["group"] == {"rate": None, "n": None}
    assert (rows["retention"]["gap_pts"], rows["retention"]["rank"]) == (None, None)


def test_the_specs_replay_through_the_builder(client: TestClient, results_file: Path) -> None:
    body = client.get(OUTCOMES).json()
    specs = body["meta"]["specs"]

    assert [spec["measure"] for spec in specs] == [row["measure"] for row in body["rows"]]
    for spec, page_row in zip(specs, body["rows"], strict=True):
        response = client.post(QUERY, json=spec)
        assert response.status_code == 200
        answer = response.json()
        men = next((r for r in answer["rows"] if r["group"]["gender"] == "M"), None)
        rate = None if men is None else men["metric_rate"]
        assert page_row["group"]["rate"] == (None if rate is None else round(rate * 100, 1))
        assert page_row["everyone"]["n"] == answer["everyone"]["denominator"]
        if page_row["rank"] is not None:
            ranked = (men["gap_pts"], men["rank_in_breakdown"], men["ranked_of"])
            assert (page_row["gap_pts"], page_row["rank"], page_row["ranked_of"]) == ranked


def test_a_refused_spec_is_a_server_problem(
    client: TestClient, publish_results: Callable[..., Path]
) -> None:
    # A manifest without persistence refuses the page's own spec: never the caller's to fix.
    publish_results(PAGES_MANIFEST.replace("  persistence: *yes_or_no\n", ""), ROWS, GAPS)

    response = client.get(OUTCOMES)

    assert response.status_code == 503
    assert "persistence" in response.json()["error"]["message"]


def test_missing_results_file_is_a_clear_error(client: TestClient, results_file: Path) -> None:
    results_file.unlink()

    response = client.get(OUTCOMES)

    assert response.status_code == 503
    assert "publish the results" in response.json()["error"]["message"]
