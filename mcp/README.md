# PDP MCP server

A local, read-only [Model Context Protocol](https://modelcontextprotocol.io/) server for the
definitions of the normalized PDP data model, part of the Query Layer. Point
an MCP-capable AI client at it, and the assistant can find the model's tables, see how they join,
and read what each column means, without seeing any student data. See
[client status](#client-status) for which clients have been checked.

**The data is synthetic.** Nothing built on it is a finding about real students or institutions.

- It runs on your machine, over stdio. Nothing is hosted.
- **Definitions mode needs no database.** It reads the repository's metadata files: the model's
  schema, the mapping configs and the data dictionaries.
- Definitions mode returns no student-level values at all. Published mode adds `query_results`,
  which reads the published success-measure results for approved specs only. Aggregate mode
  answers grouped SQL and hides small groups, but it judges a group's size by the count the query
  itself reports: see the limits and the [policy](#policy) under [Access modes](#access-modes).
- It has no embeddings or vector search.

## Access modes

What the server exposes is set by trusted configuration when it starts, never by a tool argument
or a chat message.

| `PDP_MCP_ACCESS_MODE` | What it exposes | Status |
|---|---|---|
| `definitions` (the default) | The four metadata tools below. No data-query tools, no student-level values. | Available. Needs no database |
| `published` | Those four tools plus `query_results`: slices of the published success-measure results, for specs `measures/manifest.yaml` approves. No SQL. | Available. Needs no database. Recommended for Claude Desktop and other outside clients |
| `aggregate` | Those four tools, `query_results`, and `run_aggregate_query`: read-only SQL over the loaded model, answered as groups. For exploring synthetic data only. | Available. Needs `PDP_MCP_BACKEND`, or the server stops at startup |

Aggregate mode's rules are in `pdp_mcp/aggregate.py`, applied after the query and before the result
leaves the server:

- Every result needs a column named `n`, the count of distinct students in each row's group.
  Without it the result is refused, because there is nothing to judge a group's size by.
- A result selecting `student_id`, `enrollment_id` or `attribute_id` is refused outright.
- Groups under 10 students are dropped, and the result says how many were dropped in
  `suppressed_rows`. The kept values are then checked against the `student` table, which catches a
  student ID arriving under a column named something else.

**`n` is taken on trust, so these rules bound an honest caller, not a hostile one.** Nothing checks
that `n` is really the number of distinct students in its row's group, or that the query groups at
all. `SELECT race, gender, 999 AS n FROM student WHERE race = '<a small race>'` passes every rule
and returns one row per student. Written honestly, the same query is suppressed. Treat aggregate
mode as a guard rail for a client asking in good faith, and keep the database read-only and
synthetic. Closing this properly means the server computing the counts itself, which is what
published mode does.

Aggregate mode also applies no complementary suppression: a breakdown where exactly one group is
dropped can still be worked out by subtraction from a total the caller also asks for. The shared
measures hide a second group to cover that; `run_aggregate_query` answers SQL directly, never sees
the breakdown as a set of lines, and cannot do the same.

Published mode takes `n` off trust and hands the hiding to the publisher. `query_results` takes no
SQL: it takes a spec (a measure, a cohort, a breakdown, optional filters) and answers it from the
results `measures/publish.py` wrote, checked against the manifest they were published from. The
counts are the publisher's, not the caller's. Each measure and cohort is published in one run. One run hides one set of groups, so rows from different runs can't be set against each other,
and `success_measures` and `equity_gaps` hide the same groups. Within the run, hiding has the
limits listed under [Rules](../measures/README.md#rules) in `measures/README.md`: display
protection, not a guarantee. A spec the manifest doesn't approve is refused, and the refusal lists
what is approved.

A spec can also set `min_denominator`: only groups whose published denominator is at least that
come back, and hidden groups (blank denominator) always drop out. With `include: ["rates", "gaps"]`,
each compared group gets `rank_in_breakdown` of `ranked_of`: its rank among the breakdown's compared
groups by students affected, 1 = most behind, with ties sharing a rank. It's ranked across the whole
breakdown even when `where` returns only some of its rows, so it isn't `rank_by_affected`, which
ranks across every breakdown of the measure and cohort. Both read published rows as they are: the
builder filters, sorts and ranks, and never does arithmetic on a numerator, denominator, rate or gap.

Answers through `query_results`, the Playground's results route and its chatbot hold at most 200
rows, and say `truncated` when there were more. The Playground's own pages call the builder in
Python with `query(spec, max_rows=None)` and read every row; `max_rows` isn't part of a spec, so no
outside caller can lift the cap.

`spec_sql(spec)` in `pdp_mcp/results.py` writes out the SQL the builder runs for a spec, values
included, from the same strings it executes. The Playground's chat shows it for each published-results
answer, so staff can rerun it against `measures/output/success_measures.sqlite`. It isn't part of
the `query_results` tool's output.

### Policy

The MCP server serves published aggregates: `published` mode and `query_results`. Free SQL
(`aggregate` mode and `run_aggregate_query`) is for exploring synthetic data only, because it
trusts `n` and can't apply complementary suppression. Never point it at real student data.

There is no student-level mode. Running SQL that returns student rows waits on an access-policy
decision. The query code is kept and tested, but no mode exposes it (see
[tool-contracts.md](docs/tool-contracts.md#dormant-execute_query)).

## The tools

| Tool | What it does |
|---|---|
| `list_tables` | Lists the model's 12 tables and what one row of each is. |
| `describe_table` | A table's columns, model types, nullability, primary key, foreign keys, unique groups, and the tables that point at it. |
| `get_column_definition` | What a column means: the data dictionary description, allowed codes, and where it comes from or goes to. Works for raw file columns (`Retention`) and table columns (`cohort_membership.retention`). |
| `get_database_info` | The access mode, the tools it exposes, the metadata files it reads (with checksums), and, if you configured one, whether your database is reachable. |
| `query_results` | Published and aggregate modes. One approved spec, such as `{"measure": "gateway_math", "cohort": "2021-22 + 2022-23 + 2023-24", "group_by": ["gender", "race"]}`, answered from the published results with the everyone row beside it. Hidden groups are blank, never 0. Nothing is recomputed. Optional `min_denominator`; with gaps, each group's rank within the breakdown. At most 200 rows. |
| `run_aggregate_query` | Aggregate mode only. One read-only statement over the loaded model, answered as groups: every result needs a count of distinct students named `n`, groups under 10 students are dropped, and a result selecting a row-level identifier is refused. |

The full contracts are in [docs/tool-contracts.md](docs/tool-contracts.md). The machine-readable
copy is [schemas/tools.json](schemas/tools.json).

## Set up

You need Python 3.10 or newer, and a checkout that includes the data model (`normalized-data-model/`),
whose files the server reads. You don't need to load a database. Everything below runs from the
repository root.

1. **Check your Python.** On macOS and Linux, `python` may be missing or old: use `python3`.

   ```bash
   python3 --version        # 3.10 or newer. Windows: py --version
   ```

2. **Install**, once. This is the repository's usual virtual environment; skip it if you already
   made `.venv` for another foundation.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   python -m pip install -r requirements.txt
   ```

   That installs every foundation's pinned packages, including the MCP SDK (`mcp==2.3.0`). The MCP
   server itself needs only `mcp` and `pyyaml` from that list.

3. **Check that it starts:**

   ```bash
   .venv/bin/python mcp/run_server.py < /dev/null
   echo $?                          # 0
   ```

   On Windows, in Command Prompt: `.venv\Scripts\python mcp\run_server.py < NUL`, then `echo %ERRORLEVEL%`.
   (Windows hasn't been tested.)

   No output and exit code 0 means it started, read its metadata, and stopped when its input
   closed. A problem prints `pdp-mcp: can't start: ...` and exits with code 2. A server that
   starts and then waits is normal when you leave out `< /dev/null`: it's waiting for a client.
   Press Ctrl+C.

4. **Add it to your AI client**: see [Connect a client](#connect-a-client).

5. **Check it in the client** with the [smoke test](#smoke-test). For a full manual test, see
   [docs/uat.md](docs/uat.md).

## Settings

Environment variables, read once when the server starts. Set them in your client's config (`env`),
not in a committed file. None is required.

| Variable | Default | What it does |
|---|---|---|
| `PDP_MCP_ACCESS_MODE` | `definitions` | See [Access modes](#access-modes). Anything else stops the server. |
| `PDP_MCP_BACKEND` | unset | Optional: `sqlite` or `postgres`. Only lets `get_database_info` report whether your loaded database is reachable. No tool reads it, and it adds no tools. |
| `PDP_MCP_SQLITE_PATH` | `normalized-data-model/output/pdp.sqlite` | With `PDP_MCP_BACKEND=sqlite`: the database the [loader](../normalized-data-model/README.md#load-the-data) wrote. A relative path is read from the repository root. Opened read-only, never created. |
| `PDP_MCP_POSTGRES_URL` | none | With `PDP_MCP_BACKEND=postgres`: the connection URL. Use a role that can only read (see below). |
| `PDP_MCP_RESULTS_PATH` | `measures/output/success_measures.sqlite` | The published results file `query_results` reads, written by `python -m measures.publish` beside its `.publication.json` record. A relative path is read from the repository root. Read-only; a missing file doesn't stop the server, `query_results` says so when called. |
| `PDP_MCP_LOG_LEVEL` | `WARNING` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Logs go to stderr; your client usually shows them in its MCP output panel. |

If you do point it at PostgreSQL, use a read-only role. The loader's role can write.

```sql
CREATE ROLE pdp_reader LOGIN PASSWORD 'choose-a-password';
GRANT CONNECT ON DATABASE pdp TO pdp_reader;
GRANT USAGE ON SCHEMA public TO pdp_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pdp_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE <loader_role> IN SCHEMA public GRANT SELECT ON TABLES TO pdp_reader;
```

`get_database_info` warns if the role is a superuser or can write a model table.

## Connect a client

Every client starts the same command: the repository's Python running `mcp/run_server.py`. The
launcher needs no working directory.
- Replace `/absolute/path/to/pdp-datathon-starter` with where you cloned the repository. Run `pwd`
  in it to see.
- On Windows, the Python is `.venv\Scripts\python.exe` instead of `.venv/bin/python`.
- No settings are needed for definitions mode. A client only passes the environment variables you
  put in its config, not your shell's, so put any `PDP_MCP_*` setting in the config's `env`.

### Client status

| Client | Status |
|---|---|
| Claude Code (CLI) | **Checked** on macOS, with the config below given through `--mcp-config`: all 4 tools found and used, no query tool offered. |
| Claude Desktop | Config follows Claude Desktop's documented `claude_desktop_config.json` format. **Not yet checked by hand**: walk [UAT-33](docs/uat.md#uat-33-claude-desktop) and record the result. The same server and settings were checked over stdio, which is the transport Claude Desktop uses. |
| VS Code (GitHub Copilot agent mode) | Config follows VS Code's documented `mcp.json` format. **Not yet checked by hand.** |
| Cursor | Config follows Cursor's documented `mcp.json` format. **Not yet checked by hand.** |
| Others | Any client that runs a stdio MCP server should work with the generic config. Not checked. |

If you check one, record it in [docs/uat.md](docs/uat.md).

### VS Code (GitHub Copilot agent mode)

Create `.vscode/mcp.json` in the repository. On Windows, use
`${workspaceFolder}/.venv/Scripts/python.exe` as the command.

```json
{
  "servers": {
    "pdp": {
      "type": "stdio",
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["${workspaceFolder}/mcp/run_server.py"]
    }
  }
}
```

Open the file, select **Start** above `pdp`, then open Copilot Chat in **Agent** mode and check the
tools list.

### Cursor

Create `.cursor/mcp.json` in the repository, or add the entry to `~/.cursor/mcp.json` for every
project. Use absolute paths:

```json
{
  "mcpServers": {
    "pdp": {
      "command": "/absolute/path/to/pdp-datathon-starter/.venv/bin/python",
      "args": ["/absolute/path/to/pdp-datathon-starter/mcp/run_server.py"]
    }
  }
}
```

Then open **Settings → MCP**, check `pdp` is on and shows 4 tools, and use it from Agent chat.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, or
`%APPDATA%\Claude\claude_desktop_config.json` on Windows. Merge this into the existing
`mcpServers` object rather than replacing the file, and use absolute paths for both the Python and
the launcher: Claude Desktop starts the server from an arbitrary working directory.

```json
{
  "mcpServers": {
    "pdp": {
      "command": "/absolute/path/to/pdp-datathon-starter/.venv/bin/python",
      "args": ["/absolute/path/to/pdp-datathon-starter/mcp/run_server.py"]
    }
  }
}
```

For published results, add published mode to the entry's `env`. It's the recommended mode for
Claude Desktop: it needs no database, and it answers only approved specs. Claude Desktop passes the
server none of your shell's environment, so a `PDP_MCP_*` variable exported in a terminal is
invisible to it:

```json
      "env": {
        "PDP_MCP_ACCESS_MODE": "published"
      }
```

Publish the results first (`python -m measures.publish`), or set `PDP_MCP_RESULTS_PATH` to a
published file.

Then quit Claude Desktop and reopen it: it reads the file at launch only. Ask "What tables does the
PDP data model have?" to check it. A server that fails to start says nothing in the window, so
reproduce it in a terminal with step 3 of [Set up](#set-up) and read stderr.

### Claude Code

From the repository root:

```bash
claude mcp add pdp -- "$PWD/.venv/bin/python" "$PWD/mcp/run_server.py"
```

This adds it for this project only (Claude Code's default `local` scope). `/mcp` in a session shows
its status. Or, without changing your Claude Code settings, put the [generic config](#any-other-mcp-client)
in a file and start a session with `claude --mcp-config that-file.json`. That's how it was checked.

### Any other MCP client

Any client that runs a stdio server takes the same three things:

| | Value |
|---|---|
| command | `/absolute/path/to/pdp-datathon-starter/.venv/bin/python` |
| args | `["/absolute/path/to/pdp-datathon-starter/mcp/run_server.py"]` |
| env | the [settings](#settings) you need, usually none |

Most use this shape:

```json
{"mcpServers": {"pdp": {"command": "...", "args": ["..."], "env": {}}}}
```

## Things to ask

Once connected, ask in plain language. The assistant chooses the tools. For example:

- "What tables are in the PDP data model, and how do they join?"
- "What does `Gateway_Math_Status` mean, and what codes can it have?"
- "Is `enrollment_type` in the cohort table or the student table? Which file column does it come from?"
- "Which columns could I use to break down retention by student group?"
- "Write a SQL query for first-time students' retention by Pell status. I'll run it myself."

The server can't run queries or count students: ask the assistant to write the SQL, then run it
yourself against your own database (see [Load the data](../normalized-data-model/README.md#load-the-data)).
How measures such as retention should be counted belongs to the Measures workstream.

## Example tool calls

These are the arguments a client sends. The results are shortened.

```json
// list_tables
{}
// → {"source": "normalized-data-model/config/destination_schema.yaml",
//    "tables": [{"name": "cohort_membership", "type": "table", "in_model": true,
//                "description": "student and cohort, with everything the cohort file says about that cohort"}, ...]}

// describe_table
{"table": "student"}
// → {"primary_key": ["student_id"],
//    "columns": [{"name": "student_id", "data_type": null, "model_type": "str", "nullable": false, ...}, ...],
//    "referenced_by": [{"table": "cohort_membership", "columns": ["student_id"], ...}, ...], ...}

// get_column_definition
{"column": "retention"}
// → matches: [{"kind": "source", "source_file": "pdp_cohort_data.csv", "source_column": "Retention",
//              "description": "Retention is defined as either continued enrollment ...", ...},
//             {"kind": "normalized", "table": "cohort_membership", "column": "retention", "model_type": "bool", ...}]
```

## Smoke test

After setting up, check these five things in your client:

1. **It starts.** The client shows `pdp` as running or connected. If not, run step 3 of
   [Set up](#set-up) in a terminal and read the message.
2. **In the default mode it has exactly 4 tools:** `list_tables`, `describe_table`, `get_column_definition`,
   `get_database_info`.
3. **Schema discovery works.** Ask "Describe the student table." It should give `student_id` as
   the primary key and list the 3 tables that point at it.
4. **Definitions work.** Ask "What does Retention mean?" It should quote the data dictionary.
5. **It has no data access.** Ask "How many students are there? Use the pdp tools." The assistant
   should say it has no tool for that. `get_database_info` shows `access_mode: definitions`.

In published mode, check two more: the tool list has `query_results` and `get_database_info` shows
`access_mode: published`; and asking for gateway math by race returns a row per group with the
everyone row, while asking for a breakdown the manifest doesn't list is refused with what is
approved.

In aggregate mode, check two more: the tool list has `run_aggregate_query` and
`get_database_info` shows `access_mode: aggregate`; and asking for a group of fewer than 10
students returns no row for it, with `suppressed_rows` counting what was dropped.

The tests run the same steps over stdio, with no database (`tests/test_startup.py`).

## Troubleshooting

| What you see | What to do |
|---|---|
| `can't start: PDP_MCP_ACCESS_MODE=aggregate needs a database` | Aggregate mode answers queries. Set `PDP_MCP_BACKEND` to `sqlite` or `postgres`, or unset the access mode. |
| `query_results` fails with `spec_refused` | The measure, cohort or breakdown isn't in `measures/manifest.yaml`. `error.details` lists what is approved. |
| `query_results` fails with `database_unavailable` | The results file is missing, or changed since it was published. Run `python -m measures.publish`, or check `PDP_MCP_RESULTS_PATH`. |
| `Query refused: the result needs a column named n` | Add a count of distinct students, such as `COUNT(DISTINCT student_id) AS n`. Aggregate mode judges every group by it. |
| `Query refused: results can't include row-level identifiers` | The query selects `student_id`, `enrollment_id` or `attribute_id`. Group by other columns and count students instead. |
| `can't start: can't read normalized-data-model/...` | A metadata file is missing: your checkout is incomplete or on the wrong branch. |
| The client shows the server failing with no message | Run the client's command in a terminal: the message goes to stderr. Check the paths are absolute and point at `.venv`'s Python. |
| `ModuleNotFoundError: No module named 'mcp'` | The client is using another Python. Point `command` at the repository's `.venv` Python, and install the requirements there. |
| A `PDP_MCP_*` setting seems to be ignored | Clients don't pass your shell's environment to the server. Put the setting in the client config's `env`. |
| `get_database_info` shows `database.healthy: false` | Only if you set `PDP_MCP_BACKEND`. The tools still work. The reason is in `database.error`. |
| A warning that the PostgreSQL role is a superuser or can write | Make the `pdp_reader` role above and use it. |
| Answers don't show a change you pulled or made to the data model's configs | The server reads them once, on first use. Restart it: in your client, restart or reconnect the `pdp` server. |

## Security and limits

- **Definitions only.** The registered tools read repo files and return names, types, keys,
  dictionary text and the codes the schema allows. A test sends every table and column to every tool
  with a database of sample students configured, and checks that no student ID or course name
  comes back.
- **No student-level query.** `execute_query`, which returns rows as the query wrote them, isn't
  registered in any mode, so a client can't list or call it: calling it returns `Unknown tool`.
  No setting registers it. `query_results` and `run_aggregate_query` are different tools with the
  rules above.
- **The access mode is fixed at startup** by environment variables. No tool has an argument that
  changes it.
- **No authentication.** The server trusts whoever starts it, as any local stdio server does. It
  has no network port.
- **Credentials** are read from the environment and never returned or logged by the server.
- **Small groups:** definitions mode returns no counts, so there's nothing to suppress. Published
  mode returns only what the publisher already hid, cover groups included; that hiding has the
  limits listed under [Rules](../measures/README.md#rules) in `measures/README.md`. Aggregate
  mode drops every group whose reported `n` is under 10 and says how many it dropped, and it checks
  the values it keeps against the `student` table. Two things it does not do: it does not verify
  that `n` is a real count, so a query that reports a false one is not caught; and it applies no
  complementary suppression, which the shared measures do, so a breakdown with exactly one dropped
  group, asked for beside a total, still gives that group away.

## For other workstreams

[docs/integration.md](docs/integration.md) covers the chat endpoint, the metadata assistant, the
data dictionary and the measures work, and what each workstream still needs to provide.

## Develop and test

From `mcp/`:

```bash
python -m pytest -q                         # all tests; PostgreSQL ones skip without a server
PDP_TEST_POSTGRES_URL=postgresql://user@localhost:5432/pdp_test python -m pytest -q
python -m pdp_mcp.export_schemas            # after changing a tool's arguments or output models
```

The metadata tools and `query_results` are tested over MCP, without a database: `query_results`
reads a small published file the tests write. The dormant query path and its
read-only safeguards are tested in Python, in SQLite and, with `PDP_TEST_POSTGRES_URL` set,
PostgreSQL. Those tests build their databases from the committed 10-student sample through the
loader's own table code. CI runs `make check`, which runs everything except PostgreSQL.

| File | What it is |
|---|---|
| `run_server.py` | The launcher clients start. |
| `pdp_mcp/server.py` | Registers the tools the access mode allows, and turns failures into error results. |
| `pdp_mcp/contracts.py` | The output models: the contract. |
| `pdp_mcp/metadata.py` | Tables, keys and column definitions from the repo's files. No MCP and no database: chat can import it. |
| `pdp_mcp/config.py` | The settings and access modes. |
| `pdp_mcp/results.py` | The query builder behind `query_results`: approved specs only, read from the published results. |
| `pdp_mcp/db.py`, `pdp_mcp/query.py` | SQLite and PostgreSQL, read-only. Used for `get_database_info`'s database status, and by the dormant query path. |
| `pdp_mcp/export_schemas.py` | Writes `schemas/tools.json` from the running server. |

`mcp/` has no `__init__.py` on purpose. A package named `mcp` would hide the MCP SDK, which is
also imported as `mcp`.
