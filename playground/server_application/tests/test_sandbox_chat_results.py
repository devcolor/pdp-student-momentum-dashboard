"""The query_results chat tool, called directly against a small published file."""

from pathlib import Path

import pytest

from app.sandbox.chat import results_tool
from app.sandbox.chat.metadata_tools import ToolError
from app.sandbox.results import published
from tests.published_results import COHORT, builder

SPEC = {"measure": "gateway_math", "cohort": COHORT, "group_by": ["race"]}


def error_of(arguments: dict) -> dict:
    """The MCP error body query_results raises for these arguments."""
    with pytest.raises(ToolError) as caught:
        results_tool.call(arguments)
    return caught.value.body["error"]


def test_an_approved_spec_returns_the_published_slice(published_results: Path) -> None:
    answer = results_tool.call(SPEC)

    assert answer["everyone"]["denominator"] == 3282
    assert [r["group"]["race"] for r in answer["rows"]] == [
        "Asian",
        "Native Hawaiian or Other Pacific Islander",
    ]
    # A hidden group stays blank, never 0.
    assert answer["rows"][1]["metric_rate"] is None
    assert answer["source"] == "synthetic"


def test_an_unapproved_spec_is_refused_with_the_approved_options(
    published_results: Path,
) -> None:
    error = error_of({**SPEC, "group_by": ["pell"]})

    assert error["code"] == "spec_refused"
    assert ["race"] in error["details"]["group_by"]


def test_a_badly_shaped_spec_is_an_invalid_argument(published_results: Path) -> None:
    error = error_of({"measure": "gateway_math", "group_by": "race", "sql": "SELECT 1"})

    assert error["code"] == "invalid_argument"
    assert "cohort" in error["message"]


def test_a_huge_where_value_is_an_invalid_argument(published_results: Path) -> None:
    error = error_of({**SPEC, "where": {"race": "x" * 60_000}})

    assert error["code"] == "invalid_argument"
    assert "where" in error["message"]


def test_unpublished_results_are_database_unavailable(
    tmp_path: Path, published_results: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = published_results.parent / "manifest.yaml"
    missing = tmp_path / "missing.sqlite"
    monkeypatch.setattr(published, "reader", lambda: builder.ResultsReader(manifest, missing))

    error = error_of(SPEC)

    assert error["code"] == "database_unavailable"
    assert error["details"] is None


def test_the_input_schema_is_the_builders_spec() -> None:
    assert results_tool.tool()["input_schema"] == builder.Spec.model_json_schema()
    assert results_tool.tool()["name"] == "query_results"
