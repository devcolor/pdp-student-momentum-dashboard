"""The results route: specs in, slices of a small published file out, and where it reads from."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.results import published, schemas
from tests.published_results import COHORT, MANIFEST, builder

QUERY = "/api/v1/sandbox/results/query"
APPROVED = "/api/v1/sandbox/results/approved"


def strip(schema: dict) -> dict:
    """A JSON schema without titles and descriptions, which may word things differently."""
    if isinstance(schema, dict):
        return {k: strip(v) for k, v in schema.items() if k not in ("title", "description")}
    if isinstance(schema, list):
        return [strip(v) for v in schema]
    return schema


@pytest.mark.parametrize(
    "ours, theirs",
    [
        (schemas.QuerySpec, builder.Spec),
        (schemas.ResultRow, builder.ResultRow),
        (schemas.QueryAnswer, builder.QueryAnswer),
    ],
)
def test_the_route_schemas_match_the_builder(ours, theirs) -> None:
    mine = strip(ours.model_json_schema())
    built = strip(theirs.model_json_schema())
    # Only the referenced model names differ (QuerySpec here, Spec there).
    assert json.loads(json.dumps(mine).replace("QuerySpec", "Spec")) == built


def test_an_approved_spec_returns_a_slice(client: TestClient, published_results: Path) -> None:
    response = client.post(
        QUERY, json={"measure": "gateway_math", "cohort": COHORT, "group_by": ["race"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert [r["group"]["race"] for r in body["rows"]] == [
        "Asian",
        "Native Hawaiian or Other Pacific Islander",
    ]
    assert body["rows"][1]["metric_rate"] is None
    assert body["everyone"]["denominator"] == 3282
    assert body["source"] == "synthetic"


def test_where_slices_a_two_way_breakdown(client: TestClient, published_results: Path) -> None:
    spec = {
        "measure": "gateway_math",
        "cohort": COHORT,
        "group_by": ["gender", "race"],
        "where": {"gender": "M"},
    }
    rows = client.post(QUERY, json=spec).json()["rows"]
    assert [(r["group"], r["metric_rate"]) for r in rows] == [
        ({"gender": "M", "race": "Black or African American"}, 0.1474)
    ]


def test_min_denominator_drops_hidden_and_small_groups_and_the_cap_stays(
    client: TestClient, published_results: Path
) -> None:
    spec = {
        "measure": "gateway_math",
        "cohort": COHORT,
        "group_by": ["race"],
        "min_denominator": 100,
    }
    body = client.post(QUERY, json=spec).json()
    assert [r["group"]["race"] for r in body["rows"]] == ["Asian"]
    assert body["max_rows"] == 200
    assert client.post(QUERY, json={**spec, "min_denominator": 0}).status_code == 422


def test_a_huge_where_value_is_a_422_not_a_crash(
    client: TestClient, published_results: Path
) -> None:
    spec = {
        "measure": "gateway_math",
        "cohort": COHORT,
        "group_by": ["race"],
        "where": {"race": "x" * 60_000},
    }
    assert client.post(QUERY, json=spec).status_code == 422


def test_an_unapproved_spec_is_a_400_with_what_is_approved(
    client: TestClient, published_results: Path
) -> None:
    response = client.post(
        QUERY, json={"measure": "gateway_math", "cohort": COHORT, "group_by": ["pell"]}
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "spec_refused"
    assert ["race"] in error["details"][0]["group_by"]


def test_a_bad_spec_shape_is_a_422(client: TestClient, published_results: Path) -> None:
    spec = {"measure": "dfw_rate", "cohort": COHORT, "group_by": ["a", "b", "c", "d"]}
    assert client.post(QUERY, json=spec).status_code == 422


def test_unpublished_results_are_a_503(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    missing = tmp_path / "missing.sqlite"
    monkeypatch.setattr(published, "reader", lambda: builder.ResultsReader(manifest, missing))

    response = client.post(
        QUERY, json={"measure": "gateway_math", "cohort": COHORT, "group_by": ["race"]}
    )

    assert response.status_code == 503
    assert "publish" in response.json()["error"]["message"]


def test_approved_lists_each_measure(client: TestClient, published_results: Path) -> None:
    body = client.get(APPROVED).json()
    assert body["measures"]["gateway_math"] == {
        "cohorts": [COHORT],
        "group_by": [["race"], ["gender", "race"]],
    }


def test_results_db_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESULTS_DB", "/data/results.sqlite")
    monkeypatch.setenv("DEAGGREGATION_DB", "/data/deploy_copy.sqlite")
    assert published.results_path() == Path("/data/results.sqlite")


def test_deaggregation_db_is_read_without_results_db(monkeypatch: pytest.MonkeyPatch) -> None:
    # The deploy sets only DEAGGREGATION_DB, to its trimmed copy of the same measures file.
    monkeypatch.delenv("RESULTS_DB", raising=False)
    monkeypatch.setenv("DEAGGREGATION_DB", "/data/deploy_copy.sqlite")
    assert published.results_path() == Path("/data/deploy_copy.sqlite")


def test_neither_setting_leaves_the_builder_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RESULTS_DB", raising=False)
    monkeypatch.delenv("DEAGGREGATION_DB", raising=False)
    monkeypatch.setattr(published.settings, "RESULTS_DB", None)
    monkeypatch.setattr(published.settings, "DEAGGREGATION_DB", None)
    assert published.results_path() is None


def test_an_env_file_value_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    # .env files reach settings, not os.environ, so results_path falls back to settings.
    monkeypatch.delenv("RESULTS_DB", raising=False)
    monkeypatch.delenv("DEAGGREGATION_DB", raising=False)
    monkeypatch.setattr(published.settings, "RESULTS_DB", "/data/from_env_file.sqlite")
    assert published.results_path() == Path("/data/from_env_file.sqlite")


def test_the_real_environment_beats_an_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESULTS_DB", "/data/results.sqlite")
    monkeypatch.setattr(published.settings, "RESULTS_DB", "/data/from_env_file.sqlite")
    assert published.results_path() == Path("/data/results.sqlite")
