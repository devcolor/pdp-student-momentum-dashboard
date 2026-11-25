"""query_results over MCP: published mode's one data tool, answered by the query builder (results.py).

Each test reads conftest's small published file, so none needs measures/ or a database. The data is
made up. test_results.py tests the builder itself; these test what a client sees.
"""

import anyio
import jsonschema
from mcp.client import Client

from conftest import COHORT, call, error_code
from pdp_mcp.config import Settings
from pdp_mcp.results import QueryAnswer, ResultsReader, Spec
from pdp_mcp.server import Tools, _guarded, build_server

PUBLISHED_MODE = Settings(access_mode="published")
METADATA_TOOLS = ["describe_table", "get_column_definition", "get_database_info", "list_tables"]


def reader(published):
    """A ResultsReader over the fixture's manifest and results file."""
    manifest, results = published
    return ResultsReader(manifest, results)


def listed(settings, results=None):
    """The tools a client sees, by name."""
    async def run():
        async with Client(build_server(settings, results=results)) as client:
            return {t.name: t for t in (await client.list_tools()).tools}
    return anyio.run(run)


def ask(published, **spec):
    """query_results over MCP. Returns (is_error, structured content), checked by conftest's call()."""
    return call(PUBLISHED_MODE, "query_results", spec, reader(published))


def without_titles(schema):
    """A JSON schema without its titles and descriptions, which may differ between two models."""
    if isinstance(schema, dict):
        return {k: without_titles(v) for k, v in schema.items() if k not in ("title", "description")}
    if isinstance(schema, list):
        return [without_titles(item) for item in schema]
    return schema


def test_published_mode_lists_the_metadata_tools_and_query_results():
    assert sorted(listed(PUBLISHED_MODE)) == [*METADATA_TOOLS, "query_results"]


def test_an_approved_spec_matches_the_answer_contract(published):
    is_error, answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"])
    assert not is_error, answer
    jsonschema.validate(answer, QueryAnswer.model_json_schema())   # call() checked the listed outputSchema
    assert [row["group"]["race"] for row in answer["rows"]] == [
        "Asian", "Black or African American", "Native Hawaiian or Other Pacific Islander"]
    assert answer["everyone"]["denominator"] == 3282 and answer["source"] == "synthetic"
    assert answer["spec"]["where"] == {} and answer["spec"]["include"] == ["rates"]   # Spec's defaults


def test_a_hidden_group_stays_blank_never_zero(published):
    _, answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"])
    hidden = answer["rows"][2]
    assert hidden["status"] == "suppressed"
    assert (hidden["numerator"], hidden["denominator"], hidden["metric_rate"]) == (None, None, None)


def test_where_and_gaps_pass_through(published):
    _, answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"],
                    where={"gender": "M"}, include=["rates", "gaps"])
    assert [row["group"] for row in answer["rows"]] == [{"gender": "M", "race": "Black or African American"}]
    assert answer["rows"][0]["gap_pts"] == -13.92


def test_min_denominator_and_the_ranks_pass_through_and_the_cap_stays(published):
    _, answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"],
                    include=["rates", "gaps"], min_denominator=200)
    assert [row["group"]["gender"] for row in answer["rows"]] == ["F"]
    assert answer["spec"]["min_denominator"] == 200 and answer["max_rows"] == 200
    _, answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"],
                    where={"gender": "M"}, include=["rates", "gaps"])
    assert (answer["rows"][0]["rank_in_breakdown"], answer["rows"][0]["ranked_of"]) == (1, 1)


def test_a_huge_where_value_is_refused_before_the_tool_runs(published):
    # Past SQLite's LIKE pattern limit it would crash the query; the input schema stops it first.
    async def run():
        async with Client(build_server(PUBLISHED_MODE, results=reader(published))) as client:
            return await client.call_tool("query_results", {"measure": "dfw_rate", "cohort": COHORT,
                                                            "group_by": ["course"], "where": {"course": "x" * 60_000}})
    result = anyio.run(run)
    assert result.is_error and result.structured_content is None   # the SDK's input check, a text message
    assert "where" in result.content[0].text


def test_an_unapproved_breakdown_is_refused_with_what_is_approved(published):
    is_error, content = ask(published, measure="gateway_math", cohort=COHORT, group_by=["pell"])
    assert is_error and content["error"]["code"] == "spec_refused"
    assert ["race"] in content["error"]["details"]["group_by"]


def test_an_unknown_filter_value_is_refused_with_the_values(published):
    is_error, content = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"],
                            where={"race": "Martian"})
    assert is_error and content["error"]["code"] == "spec_refused"
    assert "Asian" in content["error"]["details"]["values"]["race"]


def test_an_unpublished_results_file_is_unavailable_not_refused(published, tmp_path):
    manifest, _ = published
    missing = ResultsReader(manifest, tmp_path / "missing.sqlite")
    code = error_code(PUBLISHED_MODE, "query_results",
                      {"measure": "gateway_math", "cohort": COHORT, "group_by": ["race"]}, missing)
    assert code == "database_unavailable"


def test_four_dimensions_are_refused_before_the_tool_runs(published):
    async def run():
        async with Client(build_server(PUBLISHED_MODE, results=reader(published))) as client:
            return await client.call_tool("query_results", {"measure": "dfw_rate", "cohort": COHORT,
                                                            "group_by": ["course", "race", "gender", "pell"]})
    result = anyio.run(run)
    assert result.is_error and result.structured_content is None   # the SDK's input check, a text message
    assert "group_by" in result.content[0].text


def test_an_invalid_spec_called_in_python_is_an_invalid_argument(published):
    tools = Tools(PUBLISHED_MODE, results=reader(published))
    result = _guarded(lambda: tools.query_results(measure="dfw_rate", cohort=COHORT,
                                                  group_by=["course", "race", "gender", "pell"]))
    assert result.is_error and result.structured_content["error"]["code"] == "invalid_argument"


def test_the_input_schema_is_the_spec(published):
    schema = listed(PUBLISHED_MODE)["query_results"].input_schema
    spec = Spec.model_json_schema()
    assert without_titles(schema["properties"]) == without_titles(spec["properties"])
    assert schema["required"] == spec["required"]


def test_the_results_path_setting_is_the_file_read(published, tmp_path):
    _, results = published
    assert Tools(Settings(access_mode="published", results_path=results)).results.results_path == results
    assert Tools(PUBLISHED_MODE).results.results_path == ResultsReader().results_path
