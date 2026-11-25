# Using the PDP MCP server from other workstreams

For the chat endpoint, the metadata assistant, the data dictionary and the shared
measures. The tools and their schemas are in [tool-contracts.md](tool-contracts.md) and
[../schemas/tools.json](../schemas/tools.json). Setup is in [../README.md](../README.md). **The data
is synthetic.**

The Query Layer's goal is to let apps and coding assistants use shared measures and definitions
within agreed access limits. The default `definitions` access mode covers the definitions half:
four metadata tools, no data-query tools, no student-level values. The `published` mode covers the
measures half: the same four tools plus `query_results`, which reads the published results for
approved specs only.

**Policy.** The server serves published aggregates (`published` mode, `query_results`). Free SQL
(`aggregate` mode, `run_aggregate_query`) is for exploring synthetic data only, because it trusts
`n` and can't apply complementary suppression. Never point it at real student data.

## One source for definitions: a library and the MCP tools on top of it

Everything the four tools return comes from
[`pdp_mcp.metadata.Metadata`](../pdp_mcp/metadata.py). It's plain Python with no MCP and no
database, and it reads the repo's files. Its only dependency is PyYAML. MCP and any other consumer
give the same answers if they call it:

| Tool | Library call | Returns the same dictionaries as |
|---|---|---|
| `list_tables` | `Metadata().tables()` | `ListTablesResult.tables` |
| `describe_table` | `Metadata().describe(table)` | `DescribeTableResult` |
| `get_column_definition` | `Metadata().define(column, table, source_file)` | `ColumnDefinitionResult.matches` |
| `get_database_info` | `Metadata().status()` | `metadata.files` and its error |

`describe` and `define` raise `pdp_mcp.metadata.NotFound`, with `.suggestions`, where the tools
return `not_found`. To validate the dictionaries, use the Pydantic models in
[`pdp_mcp.contracts`](../pdp_mcp/contracts.py).

`metadata.files[].sha256` in `get_database_info`, or `Metadata().status()`, gives each source
file's checksum. Two consumers can compare them to confirm they read the same definitions.

Each `Metadata` reads every file once, together, on first use, and answers from that snapshot. Its
checksums are of those same bytes. If a file changes on disk later, for example after a `git pull`,
a running server keeps its snapshot and its checksums together; restart it, or make a new
`Metadata()`, to pick up the change.

## Chat endpoint

Either way works. Pick what fits where the chat backend runs.

**Import the library**, if the backend is Python and can see this repository:

```python
import sys
sys.path.insert(0, "/path/to/pdp-datathon-starter/mcp")
from pdp_mcp.metadata import Metadata, NotFound

metadata = Metadata()                      # reads the repo files once
metadata.describe("cohort_membership")     # dict: columns, keys, relationships
metadata.define("retention")               # list of source and normalized definitions
```

This needs PyYAML in the chat backend's environment. The playground server on `main` has its own
`pyproject.toml` (Python 3.14 or newer), so add `pyyaml` there if chat lives in it.

**Or be an MCP client:** start `mcp/run_server.py` as a subprocess and hand the model the tools from
`tools/list`. Each tool's `name`, `description` and `inputSchema` are what a function-calling API
needs. Return `structuredContent` as the tool result.

```python
import os
from mcp import Client
from mcp.client.stdio import StdioServerParameters

# The SDK passes the server only a minimal environment unless you give it one.
params = StdioServerParameters(command=".venv/bin/python", args=["mcp/run_server.py"], env=dict(os.environ))
async with Client(params) as client:
    tools = (await client.list_tools()).tools
    result = await client.call_tool("describe_table", {"table": "student"})
```

Either way:
- The access mode comes from the server's environment. A chat request can't change it, and no tool
  argument can.
- Chat should run in the same mode, with the same tool list, so both surfaces expose the same
  things.
- Chat gets no SQL tool from this server in definitions or published mode. For numbers, use
  `query_results` in published mode, or import `pdp_mcp.results.ResultsReader` directly: it's the
  same builder. If chat runs its own SQL, that's outside the policy above and needs its own access
  decision.
- Check `isError` first, and read `structuredContent`. An error without `structuredContent.error`
  is an argument the SDK rejected: treat it as `invalid_argument`. A `spec_refused` error's
  `details` lists what is approved, so the model can retry with an approved spec.

**Open:** where the chat backend runs, and whether it imports the library or uses MCP. End-to-end
parity tests between chat and MCP wait on that.

## Metadata assistant

Definitions mode is built for the rule that the assistant never sees student data. The server
registers only the four metadata tools, and none reads a table's rows. That's enforced by which
tools are registered, not by a prompt: `execute_query` doesn't exist for a client in this mode.
`allowed_values` come from the schema's rules, not from the data.

Not provided: column profiles, such as share of blanks and distinct counts. They're
computed from data, so they belong in the metadata pack, built where data access is allowed.

## Data dictionary

A database-backed `fields` table was proposed, populated from the data dictionary files,
supporting a context sidebar and field guide.

The MCP server currently exposes metadata from the repo's schema, mapping and dictionary files,
without requiring a database. `get_column_definition` returns, per column:
- `description` and `dictionary_name`, from `column_lookup.csv`
- `allowed_values`, `unknown_value` and the validation `rules`, from the schema
- `sources` and `destinations`, from the mapping configs

These approaches can coexist, provided the underlying definitions remain consistent.

Additional field classifications (such as identifier, demographic or outcome) and code meanings
(such as `C = college ready`) aren't in the current MCP contract. Before MCP is extended to
expose them, agree on the authoritative source, the data format, and how consistency will be kept between consumers.

## Shared measures

The manifest exists: [`measures/manifest.yaml`](../../measures/manifest.yaml) lists each approved
measure, its cohort grouping and its breakdowns. `python -m measures.publish` runs each measure and
cohort once, with every breakdown listed for it, and writes
`measures/output/success_measures.sqlite` beside a `success_measures.publication.json` record of
the manifest's and the file's SHA-256.

`query_results`, in published and aggregate modes, reads that file through the query builder in
[`pdp_mcp/results.py`](../pdp_mcp/results.py). It:
- answers only specs the manifest approves, and refuses any other with `spec_refused`, listing what
  is approved
- checks the file and the manifest against the publication record before every answer, and returns
  `database_unavailable` if the file is missing, unpublished or changed since
- returns the published rows unchanged: rates, statuses and notes, with a hidden group's numbers
  blank (null), never 0
- never recalculates anything, and leaves out exclusion counts, which can be under 10

Every answer is a slice of one run. One run hides one set of groups, so rows from
different runs can't be set against each other, and `success_measures` and `equity_gaps` hide the
same groups. Within the run, hiding has the limits listed under
[Rules](../../measures/README.md#rules) in `measures/README.md`: display protection, not a
guarantee. To approve a new measure, cohort or breakdown, add it
to the manifest, raise its version, and publish again. `PDP_MCP_RESULTS_PATH` points the server at
another published file; a relative path is read from the repository root.

The REST endpoint, the chatbot and the MCP server call the same builder, so they give the same
answers to the same spec.

## If the contract changes

Contract changes are listed in the pull request that makes them, with the tools and workstreams
affected. `tests/test_contracts.py` fails if `schemas/tools.json` and the server differ, so the
published file is always what the server does.
