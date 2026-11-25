"""The query_results tool: slices of the published success measures, through the one query builder.

It calls the same builder as the results route and the MCP server (mcp/pdp_mcp/results.py), so chat
quotes the published rates, gaps and notes as they are. Only specs measures/manifest.yaml approves
are answered, and a hidden group comes back blank. The data is synthetic.
"""

from functools import cache
from typing import Any

from pydantic import ValidationError

from app.sandbox.results import published

from .metadata_tools import ToolError, error_body
from .repo import RepoNotFound, import_path

NAME = "query_results"


@cache
def tool() -> dict[str, Any]:
    """The tool as an Anthropic tool definition, with the MCP server's description and schema."""
    import_path("mcp")
    from pdp_mcp import contracts  # type: ignore[import-not-found]
    from pdp_mcp.results import Spec  # type: ignore[import-not-found]

    return {
        "name": NAME,
        "description": contracts.TOOL_DESCRIPTIONS[NAME],
        "input_schema": Spec.model_json_schema(),
    }


def call(arguments: dict[str, Any]) -> dict[str, Any]:
    """Answer one spec. Raises ToolError with an MCP-shaped error body, as the MCP server does."""
    try:
        # Through the module attribute, so tests can point it at their own file.
        reader = published.reader()
        from pdp_mcp.results import Spec, SpecRefused  # type: ignore[import-not-found]
    except (RepoNotFound, ImportError) as exc:
        message = f"The published results can't be read here: {exc}."
        raise ToolError(error_body("database_unavailable", message)) from None
    try:
        answer = reader.query(Spec(**arguments))
    except ValidationError as exc:
        problems = "; ".join(_problem(error) for error in exc.errors())
        raise ToolError(error_body("invalid_argument", f"Not a valid spec: {problems}.")) from None
    except SpecRefused as exc:
        # A refusal that lists what's approved is about the spec; one without is about the file.
        if exc.approved:
            message = f"Spec refused: {exc}."
            raise ToolError(error_body("spec_refused", message, exc.approved)) from None
        message = f"The published results can't be read: {exc}."
        raise ToolError(error_body("database_unavailable", message)) from None
    return answer.model_dump(mode="json")


def sql(arguments: dict[str, Any]) -> str:
    """The SQL the builder ran for a spec call() answered, with its values written in."""
    from pdp_mcp.results import Spec, spec_sql  # type: ignore[import-not-found]

    return spec_sql(Spec(**arguments))


def _problem(error: Any) -> str:
    """One validation error as 'field: message'."""
    where = ".".join(map(str, error["loc"])) or "spec"
    return f"{where}: {error['msg']}"
