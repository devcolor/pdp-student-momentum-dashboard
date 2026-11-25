# PDP MCP server: tool contracts

Status: **verified, definitions mode.** These are the four tools the server registers in its
default access mode, `definitions`. Published and aggregate modes add tools, described below. `mcp/tests/` checks every result against these schemas
over MCP, and checks that the server lists exactly these tools. This replaces the five-tool contract
proposed earlier. [Breaking changes](#breaking-changes-from-the-proposed-five-tool-contract) lists
what changed and who it affects.

**The data is synthetic.** Nothing built on it is a finding about real students or institutions.

- **Machine-readable:** [../schemas/tools.json](../schemas/tools.json). It's exactly what the
  server's `tools/list` returns in definitions mode, for each tool: `name`, `description`,
  `inputSchema`, `outputSchema` and `annotations`. It's generated from the server (`python -m
  pdp_mcp.export_schemas`, run from `mcp/`), and a test fails if it differs, in-process or over stdio.
- **Definition:** [../pdp_mcp/contracts.py](../pdp_mcp/contracts.py) (output models) and
  [../pdp_mcp/server.py](../pdp_mcp/server.py) (tool arguments, and which tools each mode registers).
- **Server name:** `pdp-datathon`. **Transport:** stdio.

## Access modes

| Mode | Set by | Tools |
|---|---|---|
| `definitions` | the default, or `PDP_MCP_ACCESS_MODE=definitions` | `list_tables`, `describe_table`, `get_column_definition`, `get_database_info` |
| `published` | `PDP_MCP_ACCESS_MODE=published`. Needs no database | those four, plus `query_results` |
| `aggregate` | `PDP_MCP_ACCESS_MODE=aggregate`, with `PDP_MCP_BACKEND` set. Synthetic data only | those four, plus `run_aggregate_query` and `query_results` |

The mode is read once, from the environment, when the server starts. No tool takes an argument
that changes it, and the tool list never changes while the server runs. There is no student-level
mode. Aggregate mode without a database stops the server with exit code 2, because the tool it
adds needs one. Published mode reads only the published results file; a missing one doesn't stop
the server, and `query_results` returns `database_unavailable` until it's there.

The server serves published aggregates (`published`, `query_results`). Free SQL (`aggregate`,
`run_aggregate_query`) is for exploring synthetic data only, because it trusts `n` and can't apply
complementary suppression. Never point it at real student data.

`schemas/tools.json` publishes the default mode's tool list, so `query_results`' and
`run_aggregate_query`'s schemas are not in it. Their contracts are below.

## Common to every tool

**Read-only, no student-level values.** Every tool reads repo metadata files. None reads a table's
rows, and none writes anything. Each is annotated `readOnlyHint: true`, `destructiveHint: false`,
`idempotentHint: true` and `openWorldHint: false`.

**Success.** `isError: false`. `structuredContent` is the tool's result object, which matches its
`outputSchema`. `content[0].text` holds the same JSON.

**Failure.** `isError: true`, and `structuredContent` (and `content[0].text`) is:

```json
{"error": {"code": "not_found", "message": "No table named 'students' in the normalized model.", "details": {"suggestions": ["student"]}}}
```

| `code` | Means | From |
|---|---|---|
| `not_found` | no such table or column. `details.suggestions` lists close names. | `describe_table`, `get_column_definition` |
| `internal_error` | a bug or unreadable metadata. The message is generic, and the detail is logged on the server. | any tool |
| `spec_refused` | a `query_results` spec the manifest doesn't approve. `details` lists what is approved: `measures`, `cohorts`, `group_by`, or a filter's `values`. New with published mode. | `query_results` |
| `database_unavailable` | the published results file is missing, or changed since it was published. | `query_results`, and the query paths for their database |

The error schema also lists `invalid_argument`, `query_rejected`, `query_failed` and `timeout`.
They're returned by `run_aggregate_query` and the dormant query path. Definitions-mode tools never
return them, or `database_unavailable`; `get_database_info` reports an unreachable database in its
output instead.

**From the MCP SDK:** arguments that break a tool's `inputSchema` (`"table": ""`) are rejected
before the tool runs, as `isError: true` with a text message and no `structuredContent`. Treat
that as `invalid_argument`. Calling a tool that isn't registered, such as `execute_query`, returns
`isError: true` with the text `Unknown tool: <name>`.

**No credentials** appear in any result or error.

---

## `list_tables`

**Purpose.** Find out what tables the normalized model has. Usually the first call.

**Input.** None: `{}`.

**Output.** `ListTablesResult`:

| Field | Type | Meaning |
|---|---|---|
| `source` | string | `normalized-data-model/config/destination_schema.yaml`, where the tables come from |
| `tables[]` | object | by name |
| `tables[].name` | string | |
| `tables[].type` | `"table"` \| `"view"` | always `table` in definitions mode |
| `tables[].in_model` | boolean | always true in definitions mode |
| `tables[].description` | string \| null | what one row is, from "The tables" in [normalized-data-model/README.md](../../normalized-data-model/README.md) |

Only the model's 10 tables are listed. Tables or views you add to your own database aren't in
the model's schema, so they aren't listed.

**Example.**

```json
{"source": "normalized-data-model/config/destination_schema.yaml", "tables": [
  {"name": "cohort_membership", "type": "table", "in_model": true,
   "description": "student and cohort, with everything the cohort file says about that cohort"},
  {"name": "course", "type": "table", "in_model": true, "description": "course prefix and number"}
]}
```

**Errors.** `internal_error` only.

---

## `describe_table`

**Purpose.** Learn a table's columns and how it joins to the others.

**Input.**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `table` | string, 1–128 characters | yes | a name from `list_tables`. Exact match, then a case-insensitive one. |

**Output.** `DescribeTableResult`, from `destination_schema.yaml`, the file the loader creates
every table from:

| Field | Type | Meaning |
|---|---|---|
| `name`, `type`, `in_model`, `description` | | as in `list_tables` |
| `columns[]` | object | in column order |
| `columns[].name` | string | |
| `columns[].data_type` | string \| null | **always null in definitions mode.** It's a database's declared type (`TEXT`, `BIGINT`), and no database is read. |
| `columns[].model_type` | `str` \| `int` \| `float` \| `bool` \| `date` \| `datetime` | the model's type, the same in every engine |
| `columns[].nullable` | boolean | |
| `columns[].primary_key` | boolean | |
| `primary_key` | string[] | in column order |
| `foreign_keys[]` | `{columns, references_table, references_columns}` | in the order of their first column |
| `referenced_by[]` | `{table, columns, references_columns}` | other tables' foreign keys that point here, by table |
| `unique_constraints` | string[][] | each set of columns that is unique together, sorted |

A test checks that, for every model table, these columns, nullability, keys and unique groups are
exactly what SQLite and PostgreSQL report for the tables the loader built.

**Example.** `{"table": "course_enrollment"}` (most columns cut):

```json
{"name": "course_enrollment", "type": "table", "in_model": true,
 "description": "course-file row: a student in a course in a term",
 "columns": [
   {"name": "enrollment_id", "data_type": null, "model_type": "int", "nullable": false, "primary_key": true},
   {"name": "student_id", "data_type": null, "model_type": "str", "nullable": false, "primary_key": false}
 ],
 "primary_key": ["enrollment_id"],
 "foreign_keys": [
   {"columns": ["provider_id"], "references_table": "data_provider", "references_columns": ["provider_id"]},
   {"columns": ["student_id"], "references_table": "student", "references_columns": ["student_id"]},
   {"columns": ["student_id", "cohort"], "references_table": "cohort_membership", "references_columns": ["student_id", "cohort"]},
   {"columns": ["course_id"], "references_table": "course", "references_columns": ["course_id"]},
   {"columns": ["term_id"], "references_table": "term", "references_columns": ["term_id"]}
 ],
 "referenced_by": [],
 "unique_constraints": [["provider_id", "source_row_number"]]}
```

**Errors.** `not_found`, with `details.suggestions` (`students` suggests `student`).

---

## `get_column_definition`

Unchanged from the earlier five-tool contract.

**Purpose.** Find out what a column means, where it comes from, and what values it can hold,
without guessing from its name.

**Input.**

| Field | Type | Required | Meaning |
|---|---|---|---|
| `column` | string, 1–128 characters | yes | a raw file column (`Retention`, `Student_GUID`), a dictionary name (`Student ID`), a normalized column (`retention`), or `table.column` (`cohort_membership.retention`). Case doesn't matter. |
| `table` | string | no | only normalized columns of this table |
| `source_file` | string | no | only source columns of this file, such as `pdp_course_data.csv` |

**Output.** `ColumnDefinitionResult`: the arguments echoed in `query`, and `matches`, each a
**source** or a **normalized** definition, told apart by `kind`. Source matches come first.

`kind: "source"`: a column in a raw input file.

| Field | Meaning |
|---|---|
| `source_file`, `source_column` | as the file writes it |
| `dictionary_name`, `description` | from [column_lookup.csv](../../data/dictionaries/column_lookup.csv). Null if the lookup has nothing: enrichment files aren't in it. |
| `dictionary_file` | the markdown dictionary with the full entry, repo-relative |
| `destinations[]` | `{table, column}`: where the loader stores it |
| `missing_values`, `unknown_values`, `value_map` | how the file writes "no value", "unknown" and values of its own, from its mapping config. Fixes for known mock-data bugs, such as the cut-off race labels, are in `config/data_fixes.yaml` and aren't in `value_map`. |

`kind: "normalized"`: a column of a model table.

| Field | Meaning |
|---|---|
| `table`, `column` | |
| `description` | its source column's description when every source agrees. Otherwise null: read `sources[]`. |
| `model_type`, `nullable`, `primary_key`, `foreign_key`, `unique_group`, `default_value`, `unknown_value` | from `destination_schema.yaml` |
| `allowed_values` | the codes an `enum` or `value_set` rule lists, or null. These come from the schema, not the data. |
| `rules` | the rules as written in the schema, each with its `severity` |
| `sources[]` | `{source_file, source_column, dictionary_name, description}`. Empty for columns the loader makes, such as `term.sort_order`. |

**Example.** `{"column": "gender"}`:

```json
{"query": {"column": "gender", "table": null, "source_file": null},
 "matches": [
  {"kind": "source", "source_file": "pdp_cohort_data.csv", "source_column": "Gender", "dictionary_name": "Gender",
   "description": "Student gender reported to the PDP. ...", "dictionary_file": "data/dictionaries/arf_cohort_data_dictionary.md",
   "destinations": [{"table": "student", "column": "gender"}], "missing_values": [], "unknown_values": ["UK"], "value_map": {}},
  {"kind": "source", "source_file": "pdp_course_data.csv", "source_column": "Gender", "...": "..."},
  {"kind": "normalized", "table": "student", "column": "gender", "description": "Student gender reported to the PDP. ...",
   "model_type": "str", "nullable": true, "primary_key": false, "foreign_key": null, "unique_group": null,
   "default_value": null, "unknown_value": "UNKNOWN", "allowed_values": ["M", "F", "P", "X"],
   "rules": [{"enum": ["M", "F", "P", "X"], "severity": "error"}],
   "sources": [{"source_file": "pdp_cohort_data.csv", "source_column": "Gender", "dictionary_name": "Gender", "description": "..."},
               {"source_file": "pdp_course_data.csv", "source_column": "Gender", "dictionary_name": "Gender", "description": "..."}]}
 ]}
```

**Errors.** `not_found`, with `details.suggestions`, when nothing matches. It's never an empty
`matches`, and never a made-up definition.

**Not included yet.** Field classifications and the meaning of each code (`C` = college ready)
wait on the data dictionary work. `dictionary_file` and `dictionary_name` say where to
read the code meanings today.

---

## `get_database_info`

**Purpose.** Check what the server exposes and whether its sources are healthy. Call it first when
something fails.

**Input.** None: `{}`.

**Output.** `DatabaseInfoResult`:

| Field | Meaning |
|---|---|
| `access_mode` | `definitions`, `published` or `aggregate` |
| `capabilities` | the tools registered for the mode |
| `read_only` | always `true` |
| `metadata` | `{healthy, error, files: [{path, sha256}], table_count}`: the repo files the tools read, each with its SHA-256, so two consumers (MCP and chat, say) can confirm they read the same definitions. The server reads them once, on first use: the checksums are of the bytes its answers come from, until it restarts |
| `database` | null unless `PDP_MCP_BACKEND` is set. Then: `{engine, healthy, error, server_version, database, database_schema, model_tables: {expected, missing}, table_count, view_count}`. It only reports whether the database is reachable and loaded. No tool reads it. |
| `warnings` | for example, a configured database missing model tables, or a PostgreSQL role that is a superuser or can write |

`database.database` is the SQLite file's name or the PostgreSQL database's name: never a path,
host, user or password.

**Example**, with no database configured (two of the nine files shown):

```json
{"access_mode": "definitions",
 "capabilities": ["list_tables", "describe_table", "get_column_definition", "get_database_info"],
 "read_only": true,
 "metadata": {"healthy": true, "error": null, "table_count": 10, "files": [
   {"path": "normalized-data-model/config/destination_schema.yaml", "sha256": "5bce2c840b0bb75573ca9987e03287f270d926f2a7ad4edec304d3cf61815a17"},
   {"path": "normalized-data-model/config/value_sets.yaml", "sha256": "8ebfbe957bc5ab69741abef7ec516a9479a2886a860e4ad6d79b91714fa25b4e"}]},
 "database": null, "warnings": []}
```

With `PDP_MCP_BACKEND=sqlite` and a loaded database, `database` is:

```json
{"engine": "sqlite", "healthy": true, "error": null, "server_version": "3.51.2", "database": "pdp.sqlite",
 "database_schema": "main", "model_tables": {"expected": ["cohort_membership", "course", "...", "term"], "missing": []},
 "table_count": 10, "view_count": 0}
```

**Errors.** None of its own. An unreadable metadata file shows as `metadata.healthy: false`, and an
unreachable database as `database.healthy: false`, each with the reason in `error`.

---

## `run_aggregate_query`

**Registered in aggregate mode only.** The same statement check and read-only database as the
dormant path, plus the rules in `pdp_mcp/aggregate.py`, which run after the query and before the
result leaves the server.

**Purpose.** Answer a grouped question about the loaded data model without showing any group small
enough to identify its students.

**Input.** `sql`: one `SELECT`, `WITH`, `VALUES` or `EXPLAIN` statement, 1 to 5000 characters. No
parameters and no `max_rows`: the limit is the module's own, smaller than the dormant path's.

**Output.** `AggregateQueryResult`:

| Field | Meaning |
|---|---|
| `columns` | `[{name, data_type}]`, in the order the query selected them, `n` among them |
| `rows` | one array per row, in column order, after small groups were dropped |
| `row_count` | the rows returned here |
| `suppressed_rows` | rows whose group held fewer than `min_group_size` students. They are not returned, and nothing else in the result reports their values |
| `min_group_size` | the smallest group the server will show |
| `truncated`, `max_rows` | whether the query had more rows than the limit, and the limit used |
| `elapsed_ms` | how long the query took |

**The rules, in the order they are applied.**

1. A result selecting `student_id`, `enrollment_id` or `attribute_id` is refused with
   `query_rejected`. It is refused, not filtered: the caller asked the wrong question.
2. A result with no column named `n` is refused with `query_rejected`. `n` is the count of distinct
   students in each row's group, and without it there is nothing to judge a group's size by.
3. Groups under `min_group_size` are dropped and counted in `suppressed_rows`. The kept values are
   then checked against the `student` table; if any is a student ID the whole result is refused,
   which catches `SELECT student_id AS region`.

**Errors.** `query_rejected` for any of the three rules and for a statement the check refuses,
`query_failed`, `timeout`, `database_unavailable`.

**What it does not do.**

- It does not verify `n`. The rules judge a group by the count the query reports, and nothing
  checks that the count is real or that the query groups at all, so a caller writing a literal
  `999 AS n` gets unaggregated rows. The rules bound a client asking in good faith. Verifying it
  means the server computing the counts, which is the published-measures design.
- It does not apply complementary suppression: a breakdown where exactly one group is dropped,
  asked for beside a total, still gives that group away. The shared measures hide a second group to
  cover that; this tool answers SQL directly and never sees a breakdown as a set of lines.
- It does not read the published measures. `query_results`, registered beside it, does.
- `EXPLAIN` passes the statement check but no `EXPLAIN` output has an `n` column, so rule 2 always
  refuses it. It is accepted by the checker and unusable through this tool.

---

## `query_results`

**Registered in published and aggregate modes.** Answered by the query builder in
`pdp_mcp/results.py`, which the REST endpoint and the chatbot also call.

**Purpose.** Read a success measure's published rates for one cohort and an approved breakdown,
with the everyone row to compare them with, without SQL and without recomputing anything.

**Input.** A spec, as flat arguments. The input schema is `Spec`'s, and a test checks they match.

| Argument | Type | Meaning |
|---|---|---|
| `measure` | string | a measure `measures/manifest.yaml` lists, such as `gateway_math` |
| `cohort` | string | an approved cohort grouping, such as `2021-22 + 2022-23 + 2023-24` |
| `group_by` | 1 to 3 strings | an approved breakdown, such as `["gender", "race"]`. Order doesn't matter |
| `where` | object, optional | keep only groups with these values, such as `{"gender": "M"}`. Keys must be in `group_by`; each value at most 200 characters. Default `{}` |
| `include` | `"rates"` \| `"gaps"` \| `"trends"` array, optional | `"gaps"` adds each group's gap against everyone else; `"trends"` adds each row's change from the previous single cohort (manifest version 7). Default `["rates"]` |
| `min_denominator` | integer ≥ 1, optional | keep only groups whose published denominator is at least this; hidden groups (blank denominator) always drop out. Default `null` (no filter) |

```json
{"measure": "gateway_math", "cohort": "2021-22 + 2022-23 + 2023-24", "group_by": ["gender", "race"]}
```

**Output.** `QueryAnswer`:

| Field | Meaning |
|---|---|
| `spec` | the spec, with its defaults filled in |
| `everyone` | the everyone row for the measure and cohort, `group: {}` |
| `rows[]` | one per group in the breakdown, sorted by its values: `group`, `status`, `numerator`, `denominator`, `metric_rate`, `note`, and with gaps `gap_status`, `gap_pts`, `ci_low`, `ci_high`, `q_value`, `likely_noise`, `students_affected`, `rank_by_affected`, `rank_in_breakdown`, `ranked_of` |
| `rank_in_breakdown`, `ranked_of` | with gaps only: the group's rank among the breakdown's compared groups by students affected, 1 = most behind, of `ranked_of` groups. Ranked across the whole breakdown even when `where` returns fewer rows; ties share a rank. `null` for rows whose gap status isn't `ok`, and without gaps. Unlike `rank_by_affected`, which ranks across every breakdown of the measure and cohort |
| `trend_vs`, `trend_pct`, `trend_direction`, `trend_judgement`, `trend_label` | with trends only, on `everyone` and each row: the previous single cohort, the relative change in percent, `up`/`down`/`flat`, `good`/`bad`/`neutral`, and the tile's arrow wording, such as `−3.5% vs 2022-23`. `null` for a pool, a row hidden in either year, and a year the manifest's `no_trend` lists. Read from `measure_trends`, which `measures/publish.py` writes with `measures/compare.py` |
| `entering_students_trend` | with trends, for `transfer_in_share` and `part_time_share` only: `vs`, `pct`, `direction`, `judgement` and `label` for the entering students (the everyone row's denominator). `null` otherwise |
| `row_count`, `truncated`, `max_rows` | the rows returned, whether there were more than the limit, and the limit. Always 200 over MCP, REST and chat; `null` only when a Playground page reads uncapped in-process with `query(spec, max_rows=None)` |
| `data_loaded_at`, `manifest_version` | from the publication record |
| `source` | always `synthetic` |

**The rules.**

- Only specs the manifest approves are answered. Each answer is a slice of one run:
  `measures/publish.py` writes each measure and cohort once. One run hides one set of
  groups, so rows from different runs can't be set against each other, and `success_measures` and
  `equity_gaps` hide the same groups. Within the run, hiding has the limits listed under
  [Rules](../../measures/README.md#rules) in `measures/README.md`: display protection, not a
  guarantee.
- A hidden group's numbers are blank (`null`), never 0. Its `status` says why, and its `note`
  passes through, including when an effect is planted in the synthetic data.
- Nothing is recomputed. Exclusion counts are left out because they can be under 10.
- The results file and the manifest are checked against the publication record before any answer.

**Errors.** `spec_refused` for an unapproved measure, cohort or breakdown, a `where` key outside
`group_by`, or a filter value no group has; `details` lists what is approved. When `where` matches
groups but `min_denominator` filters every one out, the answer is empty (`rows: []`), not `spec_refused`.
`database_unavailable` when the results file is missing, unpublished, or changed since publishing.
More than 3 dimensions, or a `where` value over 200 characters, breaks the input schema, so the SDK rejects it before the tool runs.

---

## Dormant: `execute_query`

`execute_query` is **not registered in any access mode**, so a client can't list or call it. Its
implementation (`Tools.execute_query`, with the SQLite and PostgreSQL read-only safeguards in
`db.py` and `query.py`) is kept and tested in Python, for a later student-level access decision.
Exposing it would need that decision, a new access mode, and a contract change announced to every
workstream.

As built and tested, it takes `sql` (one `SELECT`, `WITH`, `VALUES` or `EXPLAIN` statement), optional
`params` (positional, `?` in SQLite and `%s` in PostgreSQL) and optional `max_rows`. It returns
`ExecuteQueryResult`: `columns`, `rows` as arrays, `row_count`, `truncated`, `max_rows` and
`elapsed_ms`. Its errors are `query_rejected`, `query_failed`, `timeout`, `invalid_argument` and
`database_unavailable`.

---

## Breaking changes from the proposed five-tool contract

The five-tool contract was proposed first. It was replaced before anyone integrated
it, to meet the Query Layer's access rules: definitions-only by default, no data-query tools, and
no student-level values.

| Change | Why | Who it affects |
|---|---|---|
| `execute_query` is no longer listed or callable | Definitions-only mode exposes no data-query tools. Student-level access waits on a policy decision. | Chat can't run SQL through MCP. Anyone who planned to. |
| `list_tables`: `engine` and `database_schema` replaced by `source`. Only the model's tables are listed, never views or your own tables. | The tools read the model's schema, not a database | Chat, metadata assistant |
| `describe_table`: `columns[].data_type` is now nullable, and null in definitions mode | No database is read, and engine types aren't in the schema. Use `model_type`. | Chat, dictionary UI |
| `get_database_info`: new `access_mode`, `capabilities` and `metadata`. The database fields moved under `database`, which is null without one. `param_style` and `limits` removed. | It now reports what the server exposes. The removed fields only applied to `execute_query`. | Anyone reading those fields |
| The server needs no database to start; a missing or unreachable configured database no longer stops it | The tools don't read one | Setup docs |
| `tools.json` has a new top-level `access_mode` field | The published list is the definitions mode's | Anyone reading the file |

`get_column_definition` is unchanged.

Later contract changes:

| Change | Why | Who it affects |
|---|---|---|
| New `published` access mode and `query_results` tool, also registered in aggregate mode | Serve the published measures for approved specs only | Clients that want numbers: chat, Claude Desktop |
| `AccessMode` gains `published`; `ErrorCode` gains `spec_refused` | The new mode and its refusals | Anyone branching on `access_mode` or `error.code` |

## Changing a contract

1. Change `contracts.py`, or a tool's arguments or registration in `server.py`.
2. Run `python -m pdp_mcp.export_schemas` from `mcp/`, and update this file.
3. In the pull request, say what changed, why, and which workstreams call that tool.

Adding a field to an output is safe for callers that ignore unknown fields. Renaming or removing a
field, or adding a required argument, breaks them.
