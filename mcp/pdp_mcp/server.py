"""The MCP server: registers the tools its access mode allows, against the contracts in contracts.py.

The access mode comes from trusted configuration at startup (config.py). Definitions mode registers
four metadata tools. They read the repo's metadata files, never a database, and return no
student-level values. Published mode registers those four plus query_results, which answers
manifest-approved specs from the published results file (results.py) and needs no database.
Aggregate mode registers those five plus run_aggregate_query, which answers grouped questions about
the loaded database under the rules in aggregate.py: a count of distinct students in every result,
no group under the minimum, and no row-level identifier. It trusts `n` and can't apply
complementary suppression, so it's for exploring synthetic data only.

execute_query is kept, tested and dormant: Tools.execute_query and the SQLite and PostgreSQL
safeguards in db.py and query.py still work, but no access mode registers it as a tool. It returns
rows as the query wrote them, with none of aggregate mode's rules, so exposing it is a separate
student-level access decision.

Each tool returns a CallToolResult. On success, structuredContent is the tool's result model and
the text content is the same JSON. On failure, isError is true and structuredContent is an
ErrorResult. Arguments that don't match a tool's input schema are rejected by the SDK before the
tool runs, with a text message only.
"""

import json
import logging
import time
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, ValidationError

from . import aggregate, db
from .config import Settings, from_env
from .contracts import (TOOL_DESCRIPTIONS, AggregateQueryResult, ColumnDefinitionResult, DatabaseInfoResult,
                        DescribeTableResult, ErrorCode, ErrorInfo, ErrorResult, ExecuteQueryResult,
                        ListTablesResult)
from .metadata import Metadata, NotFound
from .query import QueryRejected, check_statement
from .results import MAX_DIMENSIONS, MAX_VALUE_LENGTH, QueryAnswer, ResultsReader, Spec, SpecRefused

__all__ = ["TOOLS_BY_MODE", "ToolFailure", "Tools", "build_server"]

log = logging.getLogger(__name__)

SERVER_NAME = "pdp-datathon"
_METADATA_TOOLS = ("list_tables", "describe_table", "get_column_definition", "get_database_info")
# The tools each access mode registers. Nothing else is registered, so nothing else can be called.
TOOLS_BY_MODE = {"definitions": _METADATA_TOOLS,
                 "published": (*_METADATA_TOOLS, "query_results"),
                 "aggregate": (*_METADATA_TOOLS, "run_aggregate_query", "query_results")}
_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)


class ToolFailure(Exception):
    """Raised inside a tool to return an ErrorResult with this code."""

    def __init__(self, code: ErrorCode, message: str, details: dict | None = None):
        super().__init__(message)
        self.info = ErrorInfo(code=code, message=message, details=details)


def ok(result: BaseModel) -> CallToolResult:
    data = result.model_dump(mode="json")
    return CallToolResult(content=[TextContent(text=json.dumps(data))], structured_content=data)


def failed(info: ErrorInfo) -> CallToolResult:
    data = ErrorResult(error=info).model_dump(mode="json")
    return CallToolResult(content=[TextContent(text=json.dumps(data))], structured_content=data, is_error=True)


def _guarded(tool):
    """Run a tool body, turning each expected failure into its error result."""
    try:
        return ok(tool())
    except ToolFailure as exc:
        return failed(exc.info)
    except db.Unavailable as exc:
        return failed(ErrorInfo(code="database_unavailable", message=str(exc)))
    except Exception:
        log.exception("tool failed")   # the detail stays on the server, in stderr
        return failed(ErrorInfo(code="internal_error", message="The server hit an unexpected error. Its log (stderr) "
                                                               "has the details."))


class Tools:
    """The tool bodies. The metadata tools read repo files once; query_results reads the published
    results file per call; the query paths open a database connection per call."""

    def __init__(self, settings: Settings, metadata: Metadata | None = None, results: ResultsReader | None = None):
        self.settings = settings
        self.backend = db.backend_for(settings) if settings.backend else None
        self.metadata = metadata or Metadata()
        # The reader opens no file until the first call, so a missing results file doesn't stop the server.
        if results is None:
            results = ResultsReader(results_path=settings.results_path) if settings.results_path else ResultsReader()
        self.results = results

    def list_tables(self):
        return ListTablesResult(source="normalized-data-model/config/destination_schema.yaml",
                                tables=self.metadata.tables())

    def describe_table(self, table):
        try:
            return DescribeTableResult(**self.metadata.describe(table))
        except NotFound as exc:
            raise ToolFailure("not_found", str(exc), {"suggestions": exc.suggestions}) from None

    def execute_query(self, sql, params, max_rows):
        """Dormant: not registered as a tool in any access mode. Kept, and tested, for a later decision."""
        if self.backend is None:
            raise db.Unavailable("no database is configured: set PDP_MCP_BACKEND")
        limit = self.settings.max_rows if max_rows is None else max_rows
        if limit > self.settings.max_rows:
            raise ToolFailure("invalid_argument", f"max_rows can be at most {self.settings.max_rows}, the server's "
                                                  f"limit.", {"max_rows": self.settings.max_rows})
        try:
            sql = check_statement(sql)
            started = time.perf_counter()
            result = self.backend.execute(sql, params, limit, self.settings.query_timeout_seconds)
        except (QueryRejected, db.Rejected) as exc:
            raise ToolFailure("query_rejected", f"Query refused: {exc}.") from None
        except db.TimedOut:
            seconds = self.settings.query_timeout_seconds
            raise ToolFailure("timeout", f"The query ran longer than {seconds:g} seconds and was stopped.",
                              {"timeout_seconds": seconds}) from None
        except db.Failed as exc:
            raise ToolFailure("query_failed", f"The database couldn't run the query: {exc}",
                              {"sqlstate": exc.sqlstate} if exc.sqlstate else None) from None
        return ExecuteQueryResult(columns=result.columns, rows=result.rows, row_count=len(result.rows),
                                  truncated=result.truncated, max_rows=limit,
                                  elapsed_ms=round((time.perf_counter() - started) * 1000, 2))

    def run_aggregate_query(self, sql):
        """Run one read-only query and return only its groups of min_group_size students or more."""
        if self.backend is None:
            raise db.Unavailable("no database is configured: set PDP_MCP_BACKEND")
        timeout = self.settings.query_timeout_seconds
        try:
            statement = check_statement(sql)
            started = time.perf_counter()
            result = self.backend.execute(statement, None, aggregate.MAX_ROWS, timeout)
            count_index = aggregate.check_result_columns([column["name"] for column in result.columns])
            kept = aggregate.keep_large_groups(result.rows, count_index)
            # Second layer: a student id can arrive under a column the name check allows.
            if aggregate.holds_student_ids(self.backend, kept, timeout):
                raise QueryRejected("results can't include student ids, even under another column name. "
                                    "Group by other columns and count students instead")
        except (QueryRejected, db.Rejected) as exc:
            raise ToolFailure("query_rejected", f"Query refused: {exc}.") from None
        except db.TimedOut:
            raise ToolFailure("timeout", f"The query ran longer than {timeout:g} seconds and was stopped.",
                              {"timeout_seconds": timeout}) from None
        except db.Failed as exc:
            raise ToolFailure("query_failed", self._query_failure(str(exc)),
                              {"sqlstate": exc.sqlstate} if exc.sqlstate else None) from None
        return AggregateQueryResult(columns=result.columns, rows=kept, row_count=len(kept),
                                    suppressed_rows=len(result.rows) - len(kept),
                                    min_group_size=aggregate.MIN_GROUP_SIZE, truncated=result.truncated,
                                    max_rows=aggregate.MAX_ROWS,
                                    elapsed_ms=round((time.perf_counter() - started) * 1000, 2))

    def query_results(self, **spec):
        """Answer one manifest-approved spec from the published results."""
        try:
            answer = self.results.query(Spec(**spec))
        except ValidationError as exc:
            problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'spec'}: {e['msg']}" for e in exc.errors())
            raise ToolFailure("invalid_argument", f"Not a valid spec: {problems}.") from None
        except SpecRefused as exc:
            # A refusal that lists what's approved is about the spec; one without is about the file.
            if exc.approved:
                raise ToolFailure("spec_refused", f"Spec refused: {exc}.", exc.approved) from None
            raise ToolFailure("database_unavailable", f"The published results can't be read: {exc}.") from None
        return answer

    @staticmethod
    def _query_failure(detail: str) -> str:
        """The database's error, with a hint when the model's tables aren't loaded."""
        message = f"The database couldn't run the query: {detail}"
        if "no such table" in detail or "does not exist" in detail:
            message += (" The data model may not be loaded yet: load it with the loader "
                        "(normalized-data-model/README.md).")
        return message

    def get_column_definition(self, column, table, source_file):
        try:
            matches = self.metadata.define(column, table, source_file)
        except NotFound as exc:
            raise ToolFailure("not_found", str(exc), {"suggestions": exc.suggestions}) from None
        return ColumnDefinitionResult(query={"column": column, "table": table, "source_file": source_file},
                                      matches=matches)

    def get_database_info(self):
        problem, files = self.metadata.status()
        metadata = {"healthy": problem is None, "files": files,
                    "error": ErrorInfo(code="internal_error", message=problem) if problem else None,
                    "table_count": len(self.metadata.schema) if problem is None else 0}
        database, warnings = (self._database_status() if self.backend else (None, []))
        return DatabaseInfoResult(access_mode=self.settings.access_mode,
                                  capabilities=list(TOOLS_BY_MODE[self.settings.access_mode]), read_only=True,
                                  metadata=metadata, database=database, warnings=warnings)

    def _database_status(self):
        """The configured database's health. No metadata tool reads it; this only says if it's reachable."""
        expected = sorted(self.metadata.schema)
        status = {"engine": self.backend.engine, "healthy": False, "error": None, "server_version": None,
                  "database": getattr(self.backend, "database_name", None), "database_schema": None,
                  "model_tables": {"expected": expected, "missing": expected}, "table_count": None,
                  "view_count": None}
        warnings = []
        try:
            with self.backend.connect() as connection:
                self.backend.ping(connection)
                relations = self.backend.relations(connection)
                tables = {r.name for r in relations if r.type == "table"}
                missing = [t for t in expected if t not in tables]
                status.update(healthy=True, server_version=self.backend.server_version(connection),
                              database=self.backend.database_name, database_schema=self.backend.schema_name,
                              model_tables={"expected": expected, "missing": missing}, table_count=len(tables),
                              view_count=len(relations) - len(tables))
                warnings = self.backend.warnings(connection, [t for t in expected if t in tables])
        except db.Unavailable as exc:
            status["error"] = ErrorInfo(code="database_unavailable", message=str(exc))
        if status["healthy"] and status["model_tables"]["missing"]:
            warnings.insert(0, f"The database lacks {len(status['model_tables']['missing'])} of the model's "
                               f"tables. Load it with the loader (normalized-data-model/README.md).")
        return status, warnings


_SHARED_INSTRUCTIONS = (
    "Definitions for the normalized PDP datathon data model: its tables, columns, keys, and what each "
    "column means. Start with list_tables, then describe_table and get_column_definition.")
_INSTRUCTIONS_BY_MODE = {
    "definitions": (f"{_SHARED_INSTRUCTIONS} This server has no data-query tools and returns no "
                    f"student-level values. The data is synthetic."),
    "aggregate": (f"{_SHARED_INSTRUCTIONS} run_aggregate_query then answers grouped questions about the "
                  f"loaded data: it needs a count of distinct students named "
                  f"{aggregate.COUNT_COLUMN} in every result, drops any group under "
                  f"{aggregate.MIN_GROUP_SIZE} students, and refuses a result that selects a row-level "
                  f"identifier. It is for exploring synthetic data only. query_results reads the published "
                  f"results for manifest-approved specs: prefer it for any number you report. There is no tool "
                  f"for student-level rows. The data is synthetic."),
    "published": (f"{_SHARED_INSTRUCTIONS} query_results then reads the published success-measure results: "
                  f"only specs the manifest approves, each a slice of one publishing run, with hidden groups "
                  f"left blank. A refused spec lists what is approved. There is no SQL tool and no tool for "
                  f"student-level rows. The data is synthetic."),
}


def build_server(settings: Settings | None = None, metadata: Metadata | None = None,
                 results: ResultsReader | None = None) -> MCPServer:
    settings = settings or from_env()
    tools = Tools(settings, metadata, results)
    server = MCPServer(SERVER_NAME, instructions=_INSTRUCTIONS_BY_MODE[settings.access_mode])

    def list_tables() -> Annotated[CallToolResult, ListTablesResult]:
        return _guarded(lambda: tools.list_tables())

    def describe_table(
        table: Annotated[str, Field(min_length=1, max_length=128,
                                    description="A table name from list_tables, such as cohort_membership.")],
    ) -> Annotated[CallToolResult, DescribeTableResult]:
        return _guarded(lambda: tools.describe_table(table))

    def get_column_definition(
        column: Annotated[str, Field(min_length=1, max_length=128, description=(
            "A raw file column (Retention, Student_GUID), a dictionary name (Student ID), a normalized column "
            "(retention), or `table.column`. Matching ignores case."))],
        table: Annotated[str | None, Field(
            max_length=128, description="Only normalized columns of this table.")] = None,
        source_file: Annotated[str | None, Field(
            max_length=128, description="Only source columns of this file, such as pdp_course_data.csv.")] = None,
    ) -> Annotated[CallToolResult, ColumnDefinitionResult]:
        return _guarded(lambda: tools.get_column_definition(column, table, source_file))

    def get_database_info() -> Annotated[CallToolResult, DatabaseInfoResult]:
        return _guarded(lambda: tools.get_database_info())

    def run_aggregate_query(
        sql: Annotated[str, Field(min_length=1, max_length=5000, description=(
            "One read-only statement. It must select a count of distinct students named "
            f"{aggregate.COUNT_COLUMN}, such as COUNT(DISTINCT student_id) AS {aggregate.COUNT_COLUMN}."))],
    ) -> Annotated[CallToolResult, AggregateQueryResult]:
        return _guarded(lambda: tools.run_aggregate_query(sql))

    # Flat parameters mirroring Spec, so the listed input schema is Spec's: same types, limits and defaults.
    spec_fields = Spec.model_fields

    def query_results(
        measure: Annotated[str, Field(description=spec_fields["measure"].description)],
        cohort: Annotated[str, Field(description=spec_fields["cohort"].description)],
        group_by: Annotated[list[str], Field(min_length=1, max_length=MAX_DIMENSIONS,
                                             description=spec_fields["group_by"].description)],
        where: Annotated[dict[str, Annotated[str, Field(max_length=MAX_VALUE_LENGTH)]], Field(
            default_factory=spec_fields["where"].default_factory, description=spec_fields["where"].description)],
        include: Annotated[list[Literal["rates", "gaps", "trends"]], Field(
            default_factory=spec_fields["include"].default_factory,
            description=spec_fields["include"].description)],
        min_denominator: Annotated[int | None, Field(
            ge=1, description=spec_fields["min_denominator"].description)] = None,
    ) -> Annotated[CallToolResult, QueryAnswer]:
        return _guarded(lambda: tools.query_results(measure=measure, cohort=cohort, group_by=group_by,
                                                    where=where, include=include, min_denominator=min_denominator))

    available = {fn.__name__: fn for fn in (list_tables, describe_table, get_column_definition,
                                            get_database_info, run_aggregate_query, query_results)}
    for name in TOOLS_BY_MODE[settings.access_mode]:
        server.add_tool(available[name], description=TOOL_DESCRIPTIONS[name], annotations=_READ_ONLY)
    return server
