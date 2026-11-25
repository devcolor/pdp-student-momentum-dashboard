"""Known-answer tests for the unmet need page, read from published results through the builder."""

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.aid_momentum import results
from app.sandbox.chat import query_tool
from tests.published_results import PAGES_MANIFEST, gap, row

BANDS = "/api/v1/sandbox/aid-momentum/bands"
GAPS = "/api/v1/sandbox/aid-momentum/gaps"
PELL = "/api/v1/sandbox/aid-momentum/pell"
QUERY = "/api/v1/sandbox/results/query"

SOURCE = "synthetic: test fixture, seed 1, planted effect 0.5"
NEED = "unmet_need_band"

# 200 students, as the measures would publish them. Retention is planted per band:
#   $0      50 of 60 = 83.3%    $2-5k   12 of 60 = 20.0%    UNKNOWN (no aid row): hidden as cover
#   $1-2k   30 of 60 = 50.0%    $5k+    5 students, hidden   everyone  100 of 200 = 50.0%
# Pell splits the same 200 three ways: 120 Y, 40 N, 40 unknown.
ROWS = [
    row("all", "all", 0.5, 200, "retention"),
    row(NEED, "$0", 50 / 60, 60, "retention"),
    row(NEED, "$1-2k", 0.5, 60, "retention"),
    row(NEED, "$2-5k", 0.2, 60, "retention"),
    row(NEED, "$5k+", None, None, "retention"),
    row(NEED, "UNKNOWN", None, None, "retention"),
    row("pell", "Y", 0.55, 120, "retention"),
    row("pell", "N", 0.45, 40, "retention"),
    row("pell", "UNKNOWN", 0.4, 40, "retention"),
    # Two graded enrollments each, one of them a DFW, so every shown band reads 50%.
    row("all", "all", 0.5, 400, "dfw_rate"),
    row(NEED, "$0", 0.5, 120, "dfw_rate"),
    row(NEED, "$1-2k", 0.5, 120, "dfw_rate"),
]
# Two band gaps for retention, one real and one flagged as noise, and a band never compared.
GAPS_SAVED = [
    gap(NEED, "$5k+", -23.34, -50, measure="retention"),
    gap(NEED, "$2-5k", -1.82, -5, likely_noise=True, measure="retention"),
    gap(NEED, "UNKNOWN", None, None, measure="retention", status="unknown_group"),
]


@pytest.fixture
def results_file(publish_results: Callable[..., Path]) -> Path:
    """The aid rows and gaps, published."""
    return publish_results(PAGES_MANIFEST, ROWS, GAPS_SAVED)


@pytest.fixture
def model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the read-only backend at a data model whose aid rows name where they came from."""
    path = tmp_path / "model.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE student_attribute (student_id TEXT, term_id INTEGER, attribute_key TEXT,"
        " attribute_value TEXT, source TEXT)"
    )
    connection.executemany(
        "INSERT INTO student_attribute VALUES (?, 900, 'unmet_need_band', '$0', ?)",
        [(f"s{index}", SOURCE) for index in range(3)],
    )
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


@pytest.mark.usefixtures("results_file")
def test_bands_return_the_planted_rate_for_every_band(client: TestClient) -> None:
    body = client.get(BANDS, params={"measure": "retention"}).json()

    assert body["meta"]["source"] == "synthetic"
    assert [(row["band"], row["rate"], row["n"]) for row in body["rows"]] == [
        ("$0", 83.3, 60),
        ("$1-2k", 50.0, 60),
        ("$2-5k", 20.0, 60),
        ("$5k+", None, None),  # 5 students, so hidden
        ("UNKNOWN", None, None),  # no aid row; hidden as cover for $5k+
        ("everyone", 50.0, 200),
    ]
    assert [row["is_everyone"] for row in body["rows"]] == [False] * 5 + [True]


@pytest.mark.usefixtures("results_file")
def test_a_hidden_band_keeps_its_row_and_never_reads_as_zero(client: TestClient) -> None:
    rows = client.get(BANDS, params={"measure": "retention"}).json()["rows"]
    hidden = next(row for row in rows if row["band"] == "$5k+")
    assert hidden["rate"] is None and hidden["n"] is None


@pytest.mark.usefixtures("results_file", "model_db")
def test_bands_name_the_file_and_the_planted_effect(client: TestClient) -> None:
    definitions = client.get(BANDS, params={"measure": "retention"}).json()["meta"]["definitions"]
    assert definitions["Where the bands come from"] == SOURCE
    assert "--effect 0" in definitions["Planted effect"]
    assert "finding about real students" in definitions["Planted effect"]


@pytest.mark.usefixtures("results_file")
def test_an_unreadable_data_model_only_drops_the_provenance(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> None:
        raise RuntimeError("no data model here")

    monkeypatch.setattr(query_tool, "backend", broken)

    for endpoint in (BANDS, PELL):
        response = client.get(endpoint, params={"measure": "retention"})
        assert response.status_code == 200
        definitions = response.json()["meta"]["definitions"]
        assert "Where the bands come from" not in definitions
        assert "--effect 0" in definitions["Planted effect"]


@pytest.mark.usefixtures("results_file")
def test_the_takeaway_names_the_spread_and_calls_the_gradient_planted(client: TestClient) -> None:
    takeaway = client.get(BANDS, params={"measure": "retention"}).json()["meta"]["takeaway"]
    assert "63.3 points" in takeaway  # 83.3 at $0 down to 20.0 at $2-5k
    assert "not tested for noise" in takeaway
    assert "plants that gradient" in takeaway


@pytest.mark.usefixtures("results_file")
def test_dfw_reads_the_other_way_round(client: TestClient) -> None:
    definitions = client.get(BANDS, params={"measure": "dfw_rate"}).json()["meta"]["definitions"]
    assert definitions["Reading this"].startswith("A higher rate is worse")


@pytest.mark.usefixtures("results_file")
def test_gaps_return_the_saved_rows_with_the_noise_check(client: TestClient) -> None:
    body = client.get(GAPS, params={"measure": "retention"}).json()

    shown = [
        (row["band"], row["gap_pts"], row["likely_noise"], row["rank"]) for row in body["rows"]
    ]
    assert shown == [
        ("$5k+", -23.34, False, 1),
        ("$2-5k", -1.82, True, 2),
    ]
    assert [row["ranked_of"] for row in body["rows"]] == [2, 2]
    assert body["meta"]["takeaway"].startswith("1 of 2 band gaps clear the noise check")


@pytest.mark.usefixtures("results_file")
def test_gaps_say_why_a_measure_the_gap_finder_skips_has_no_rows(client: TestClient) -> None:
    body = client.get(GAPS, params={"measure": "dfw_rate"}).json()
    assert body["rows"] == []
    assert "doesn't test" in body["meta"]["takeaway"]
    assert body["meta"]["specs"] == []  # nothing was read


def test_without_a_results_file_every_chart_is_unavailable(
    client: TestClient, results_file: Path
) -> None:
    results_file.unlink()
    for endpoint in (BANDS, GAPS, PELL):
        response = client.get(endpoint, params={"measure": "retention"})
        assert response.status_code == 503
        assert "publish the results" in response.json()["error"]["message"]


def test_a_refused_spec_is_a_server_problem(
    client: TestClient, publish_results: Callable[..., Path]
) -> None:
    # Without dfw_rate by unmet need band in the manifest, the page's own spec is refused.
    publish_results(PAGES_MANIFEST.replace("    - [unmet_need_band]\n  midterm", "  midterm"), ROWS)

    response = client.get(BANDS, params={"measure": "dfw_rate"})

    assert response.status_code == 503
    assert "isn't approved" in response.json()["error"]["message"]


@pytest.mark.usefixtures("results_file")
def test_pell_puts_the_real_field_beside_the_synthetic_bands(client: TestClient) -> None:
    body = client.get(PELL, params={"measure": "retention"}).json()

    pell = [row for row in body["rows"] if row["series"] == "pell"]
    bands = [row for row in body["rows"] if row["series"] == "unmet_need_band"]
    assert [row["group"] for row in pell] == ["Pell recipients", "No Pell", "Pell unknown"]
    assert all(row["is_real"] for row in pell)
    assert not any(row["is_real"] for row in bands)
    # Pell splits every student three ways, so its denominators add back to everyone.
    assert sum(row["n"] for row in pell) == 200
    # The band half must agree with the bands endpoint, hidden band included.
    from_bands = client.get(BANDS, params={"measure": "retention"}).json()["rows"]
    assert [(row["group"], row["rate"]) for row in bands] == [
        (row["band"], row["rate"]) for row in from_bands if not row["is_everyone"]
    ]


@pytest.mark.usefixtures("results_file")
def test_pell_explains_the_u_code_that_is_not_in_the_dictionary(client: TestClient) -> None:
    definitions = client.get(PELL, params={"measure": "retention"}).json()["meta"]["definitions"]
    assert "7.4% of rows hold U" in definitions["Pell_Status_First_Year"]


@pytest.mark.usefixtures("results_file")
def test_the_specs_replay_through_the_builder(client: TestClient) -> None:
    pell = client.get(PELL, params={"measure": "retention"}).json()
    pell_spec, band_spec = pell["meta"]["specs"]
    assert (pell_spec["group_by"], band_spec["group_by"]) == (["pell"], [NEED])

    answer = client.post(QUERY, json=pell_spec).json()
    assert {r["group"]["pell"]: r["denominator"] for r in answer["rows"]} == {
        "N": 40,
        "UNKNOWN": 40,
        "Y": 120,
    }
    bands = client.get(BANDS, params={"measure": "retention"}).json()
    assert bands["meta"]["specs"] == [band_spec]

    (gaps_spec,) = client.get(GAPS, params={"measure": "retention"}).json()["meta"]["specs"]
    replayed = client.post(QUERY, json=gaps_spec).json()["rows"]
    ranked = sorted(
        (r["rank_in_breakdown"], r["group"][NEED], r["gap_pts"])
        for r in replayed
        if r["gap_status"] == "ok"
    )
    assert ranked == [(1, "$5k+", -23.34), (2, "$2-5k", -1.82)]


def test_the_page_pools_cohorts_so_one_year_cannot_be_differenced_out() -> None:
    assert results.COHORT_YEARS == ("2021-22", "2022-23", "2023-24")
    assert results.COHORT == "2021-22 + 2022-23 + 2023-24"


def test_an_unsupported_measure_is_refused(client: TestClient) -> None:
    assert client.get(BANDS, params={"measure": "not_a_measure"}).status_code == 422
