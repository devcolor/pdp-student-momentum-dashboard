"""Checks aggregate mode: which tools it registers, and the rules a result must pass.

run_aggregate_query isn't in schemas/tools.json, which publishes the default mode's contract, so
these call it in Python through Tools and check it against AggregateQueryResult, the way
conftest.query() checks the dormant path.

The database is the committed 10-student sample: 10 students over 11 cohort_membership rows in 4
cohorts (1, 4, 3, 3). Every cohort is under the minimum, and the whole sample is exactly at it, so
the sample tests both sides of the threshold.
"""

import anyio
import jsonschema
import pytest
from mcp.client import Client
from pdp_mcp import aggregate
from pdp_mcp.config import Settings
from pdp_mcp.contracts import AggregateQueryResult
from pdp_mcp.query import QueryRejected
from pdp_mcp.server import Tools, _guarded, build_server

from conftest import ERROR_SCHEMA

RESULT_SCHEMA = AggregateQueryResult.model_json_schema()
STUDENTS = 10   # the sample's student count, which is exactly MIN_GROUP_SIZE


def aggregate_query(settings, sql):
    """run_aggregate_query, called in Python. Returns (is_error, content), checked against its contract."""
    result = _guarded(lambda: Tools(settings).run_aggregate_query(sql))
    jsonschema.validate(result.structured_content, ERROR_SCHEMA if result.is_error else RESULT_SCHEMA)
    return result.is_error, result.structured_content


def refusal(settings, sql):
    is_error, content = aggregate_query(settings, sql)
    assert is_error, content
    assert content["error"]["code"] == "query_rejected", content
    return content["error"]["message"]


def listed_tools(settings):
    async def run():
        async with Client(build_server(settings)) as client:
            return sorted(tool.name for tool in (await client.list_tools()).tools)

    return anyio.run(run)


# The rules on their own

def test_the_count_column_is_found_whatever_its_case():
    assert aggregate.check_result_columns(["cohort", "N"]) == 1
    assert aggregate.check_result_columns(["n", "cohort"]) == 0


@pytest.mark.parametrize("identifier", sorted(aggregate.ROW_ID_COLUMNS))
def test_a_row_level_identifier_is_refused(identifier):
    with pytest.raises(QueryRejected, match=identifier):
        aggregate.check_result_columns([identifier, "n"])


def test_a_result_without_a_count_column_is_refused():
    with pytest.raises(QueryRejected, match="needs a column named n"):
        aggregate.check_result_columns(["cohort", "students"])


def test_the_threshold_keeps_a_group_at_the_minimum_and_drops_one_under_it():
    rows = [["a", aggregate.MIN_GROUP_SIZE], ["b", aggregate.MIN_GROUP_SIZE - 1]]
    assert aggregate.keep_large_groups(rows, 1) == [["a", aggregate.MIN_GROUP_SIZE]]


@pytest.mark.parametrize("count", [None, "many", True, False])
def test_a_count_that_isnt_a_number_drops_its_row(count):
    # True is an int in Python, so a boolean would otherwise pass as 1 and look like a real count.
    assert aggregate.keep_large_groups([["a", count]], 1) == []


# The tool, against a loaded database

def test_a_group_at_the_minimum_is_returned(settings):
    is_error, content = aggregate_query(
        settings, "SELECT 'everyone' AS who, COUNT(DISTINCT student_id) AS n FROM student")
    assert not is_error, content
    assert content["rows"] == [["everyone", STUDENTS]]
    assert (content["row_count"], content["suppressed_rows"]) == (1, 0)
    assert content["min_group_size"] == aggregate.MIN_GROUP_SIZE


def test_every_small_group_is_dropped_and_counted(settings):
    is_error, content = aggregate_query(
        settings, "SELECT cohort, COUNT(DISTINCT student_id) AS n FROM cohort_membership GROUP BY cohort")
    assert not is_error, content
    # The sample's four cohorts hold 1, 4, 3 and 3 students, so none of them may be shown.
    assert content["rows"] == [] and content["row_count"] == 0
    assert content["suppressed_rows"] == 4


def test_a_result_without_a_count_is_refused_by_the_tool(settings):
    message = refusal(settings, "SELECT cohort FROM cohort_membership GROUP BY cohort")
    assert "needs a column named n" in message


def test_a_result_that_selects_a_student_id_is_refused(settings):
    message = refusal(settings, "SELECT student_id, COUNT(*) AS n FROM cohort_membership GROUP BY student_id")
    assert "row-level identifiers" in message and "student_id" in message


def test_a_student_id_under_another_column_name_is_refused(settings):
    """The column-name check passes here, so only the check against the student table catches it."""
    message = refusal(
        settings, "SELECT MIN(student_id) AS who, COUNT(DISTINCT student_id) AS n FROM student")
    assert "student ids" in message


def test_a_write_is_refused_before_it_reaches_the_database(settings):
    assert "only SELECT" in refusal(settings, "UPDATE student SET student_id = 'x'")


def test_a_missing_table_says_the_model_may_not_be_loaded(settings):
    is_error, content = aggregate_query(settings, "SELECT COUNT(*) AS n FROM not_a_table")
    assert is_error and content["error"]["code"] == "query_failed"
    assert "may not be loaded" in content["error"]["message"]


def test_the_tool_needs_a_database():
    is_error, content = aggregate_query(Settings(access_mode="aggregate"), "SELECT 1 AS n")
    assert is_error and content["error"]["code"] == "database_unavailable"
    assert "PDP_MCP_BACKEND" in content["error"]["message"]


# Known limits, pinned so a change in them is visible

def test_a_false_count_is_not_caught(settings):
    """The rules read n out of the result, so a caller who reports a false one is not caught.

    This pins a known limit, not a wanted behaviour: the same query written honestly is suppressed
    (see the test below). Closing it means the server computing the counts instead of reading one.
    """
    is_error, content = aggregate_query(
        settings, "SELECT cohort, 999 AS n FROM cohort_membership WHERE cohort = '2024-25'")
    assert not is_error, content
    assert content["rows"] and content["suppressed_rows"] == 0
    # The sample has one 2024-25 student, so an honest count would have hidden this row.


def test_the_same_query_with_an_honest_count_is_suppressed(settings):
    # GROUP BY, which PostgreSQL requires beside an aggregate and SQLite does not.
    is_error, content = aggregate_query(
        settings, "SELECT cohort, COUNT(DISTINCT student_id) AS n FROM cohort_membership "
                  "WHERE cohort = '2024-25' GROUP BY cohort")
    assert not is_error, content
    assert content["rows"] == [] and content["suppressed_rows"] == 1


def test_explain_is_accepted_by_the_checker_but_has_no_count(settings):
    """EXPLAIN passes check_statement, so rule 2 is what refuses it. Worth knowing when it changes."""
    assert "needs a column named n" in refusal(settings, "EXPLAIN SELECT COUNT(*) AS n FROM student")


# Which tools each mode registers

def test_definitions_mode_registers_no_query_tool():
    assert "run_aggregate_query" not in listed_tools(Settings())


def test_aggregate_mode_registers_the_four_metadata_tools_and_the_query_tools(sqlite_path):
    tools = listed_tools(Settings(access_mode="aggregate", backend="sqlite", sqlite_path=sqlite_path))
    assert tools == ["describe_table", "get_column_definition", "get_database_info", "list_tables",
                     "query_results", "run_aggregate_query"]


def test_execute_query_stays_unregistered_in_aggregate_mode(sqlite_path):
    """Aggregate mode adds the suppressed tool, not the dormant student-level one."""
    assert "execute_query" not in listed_tools(
        Settings(access_mode="aggregate", backend="sqlite", sqlite_path=sqlite_path))


def test_database_info_reports_the_mode_and_its_tools(sqlite_path):
    info = Tools(Settings(access_mode="aggregate", backend="sqlite", sqlite_path=sqlite_path)).get_database_info()
    assert info.access_mode == "aggregate"
    assert "run_aggregate_query" in info.capabilities
