"""The MCP server's four definitions tools, called through its library instead of over MCP.

Same names, input schemas and results as mcp/schemas/tools.json, so chat and the MCP server
expose the same things. Like the server's definitions mode, they read the repo's metadata files,
never a database, and have no query tool.
"""

import json
from functools import cache
from typing import Any

from .repo import import_path, repo_root

TOOL_NAMES = ("list_tables", "describe_table", "get_column_definition", "get_database_info")


class ToolError(Exception):
    """A tool couldn't answer; carries the MCP ErrorResult body."""

    def __init__(self, body: dict[str, Any]):
        super().__init__(body["error"]["message"])
        self.body = body


@cache
def tool_schemas() -> list[dict[str, Any]]:
    """The four tools as Anthropic tool definitions, from the MCP server's published contract."""
    published = json.loads((repo_root() / "mcp/schemas/tools.json").read_text(encoding="utf-8"))
    return [
        {"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
        for t in published["tools"]
        if t["name"] in TOOL_NAMES
    ]


@cache
def _library() -> tuple[Any, Any, Any]:
    """(Metadata instance, NotFound, contracts module), imported once."""
    import_path("mcp")
    from pdp_mcp import contracts  # type: ignore[import-not-found]
    from pdp_mcp.metadata import Metadata, NotFound  # type: ignore[import-not-found]

    return Metadata(repo_root=repo_root()), NotFound, contracts


def call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run one definitions tool. Raises ToolError with an MCP-shaped error body."""
    metadata, not_found, contracts = _library()
    try:
        result = _run(name, arguments, metadata, contracts)
    except not_found as exc:
        details = {"suggestions": exc.suggestions}
        raise ToolError(error_body("not_found", str(exc), details)) from None
    except (KeyError, TypeError) as exc:
        message = f"Bad arguments for {name}: {exc}"
        raise ToolError(error_body("invalid_argument", message)) from None
    return result.model_dump(mode="json")


def _run(name: str, arguments: dict[str, Any], metadata: Any, contracts: Any) -> Any:
    """Build the tool's contract model, as mcp/pdp_mcp/server.py's Tools does."""
    if name == "list_tables":
        return contracts.ListTablesResult(
            source="normalized-data-model/config/destination_schema.yaml",
            tables=metadata.tables(),
        )
    if name == "describe_table":
        return contracts.DescribeTableResult(**metadata.describe(arguments["table"]))
    if name == "get_column_definition":
        column, table = arguments["column"], arguments.get("table")
        source_file = arguments.get("source_file")
        return contracts.ColumnDefinitionResult(
            query={"column": column, "table": table, "source_file": source_file},
            matches=metadata.define(column, table, source_file),
        )
    if name == "get_database_info":
        return _database_info(metadata, contracts)
    raise ToolError(error_body("invalid_argument", f"Unknown tool: {name}"))


def _capabilities() -> list[str]:
    """Every tool this chat gives the model, which is what get_database_info has to report."""
    from . import dictionary_tool, query_tool, results_tool

    return [*TOOL_NAMES, dictionary_tool.NAME, results_tool.NAME, query_tool.NAME]


def _database_info(metadata: Any, contracts: Any) -> Any:
    """What this chat can do, and whether its database answers.

    It used to report `definitions` mode, the four metadata tools and no database, while the chat
    held query_results and run_aggregate_query the whole time. A model that asked what it could do
    was told it had no way to query and gave up instead of running a query that would have worked.

    The MCP server builds this from its own Tools, which can't be imported here: pdp_mcp.server
    needs the MCP SDK, which the API doesn't install. So the shape is built again, from the same
    contracts and the same backend the query tool uses.
    """
    from . import query_tool

    db, _, _ = query_tool._mcp()
    problem, files = metadata.status()
    expected = sorted(metadata.schema)
    status = {
        "engine": "sqlite",
        "healthy": False,
        "error": None,
        "server_version": None,
        "database": None,
        "database_schema": None,
        "table_count": None,
        "view_count": None,
        "model_tables": {"expected": expected, "missing": expected},
    }
    warnings: list[str] = []
    try:
        backend = query_tool.backend()
        status["engine"] = backend.engine
        with backend.connect() as connection:
            backend.ping(connection)
            relations = backend.relations(connection)
            tables = {r.name for r in relations if r.type == "table"}
            missing = [name for name in expected if name not in tables]
            status.update(
                healthy=True,
                server_version=backend.server_version(connection),
                database=backend.database_name,
                database_schema=backend.schema_name,
                model_tables={"expected": expected, "missing": missing},
                table_count=len(tables),
                view_count=len(relations) - len(tables),
            )
            warnings = backend.warnings(connection, [name for name in expected if name in tables])
    except db.Unavailable as exc:
        status["error"] = {"code": "database_unavailable", "message": str(exc), "details": None}
    if status["healthy"] and status["model_tables"]["missing"]:
        warnings.insert(
            0,
            f"The database lacks {len(status['model_tables']['missing'])} of the "
            f"model's tables. Load it from the Sandbox pipeline page.",
        )
    return contracts.DatabaseInfoResult(
        access_mode="aggregate",
        capabilities=_capabilities(),
        read_only=True,
        metadata={
            "healthy": problem is None,
            "files": files,
            "error": error_body("internal_error", problem)["error"] if problem else None,
            "table_count": len(metadata.schema) if problem is None else 0,
        },
        database=status,
        warnings=warnings,
    )


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """An MCP ErrorResult body."""
    return {"error": {"code": code, "message": message, "details": details}}
