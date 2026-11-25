# Architecture

How the data gets from the analysis-ready CSVs to a chart in the browser, and where each number is
computed. The data is synthetic: nothing here is a finding about real students or institutions.

```text
data/raw/*.csv + normalized-data-model/data/input/enrichment/*.csv
  -> normalized data model (SQLite)      normalized-data-model/
  -> measures and gaps, published once   measures/, gap_finder/
  -> FastAPI, one module per view        playground/server_application/app/sandbox/
  -> Next.js views and chat panel        playground/client_application/src/
  -> Anthropic API (chat only)
```

## 1. Analysis-ready CSVs to the normalized model

- **Inputs:** the PDP cohort and course files in `data/raw/`, and the synthetic enrichment files in
  `normalized-data-model/data/input/enrichment/` (housing, financial aid, student matrix, affinity,
  home state, a supplemental sample and midterm grades), plus a list of public institution events
  (`institution_events.csv`). `normalized-data-model/config/pipeline.yaml`
  lists them, in load order.
- **Steps** (`normalized-data-model/src/`): the Mapper (`mapper/`) writes each file's columns to the
  model's tables using `config/*_mapping.yaml`; the Fixer (`fixer/`) applies
  `config/data_fixes.yaml` for known mock-data bugs; the validator (`validator/`) checks every value
  against `config/destination_schema.yaml` and `config/value_sets.yaml`; the loader (`loader/`)
  replaces the tables in one transaction.
- **Output:** `normalized-data-model/output/pdp.sqlite` (or PostgreSQL), plus a CSV per table in
  `output/tables/`. Run it with `python -m src.loader.load` from `normalized-data-model/`.
- **What each column means:** `normalized-data-model/config/column_dictionary.yaml`, built from
  `data/dictionaries/`.

The Playground loads the same model into its own database (the one `DATABASE_URL` names) through
`POST /api/v1/sandbox/pipeline/runs`, which calls the same loader
(`playground/server_application/app/sandbox/pipeline/service.py`). Workbench uploads go through
that endpoint too.

## 2. Measures and gaps

- **What's published:** [measures/manifest.yaml](../measures/manifest.yaml) lists each approved
  measure, cohort and breakdown. Only what it lists is published.
- **Each measure's calculation:** `measures/calculations/`, one file per measure (`retention.py`,
  `persistence.py`, `gateway_math.py`, `gateway_english.py`, `dfw.py`, `credit_completion.py`,
  `fall_to_spring_retention.py`, `first_fall_good_standing.py`, `midterm_alert.py`,
  `midterm_recovery.py`, `completion.py`), run by `measures/run_measures.py`. Groups under 10
  students are hidden, and a second group is hidden when the first could be worked out by
  subtraction.
- **Gaps:** `gap_finder/find_gaps.py` and `gap_finder/compare.py` compare each group with everyone
  else in the same run, with a Newcombe interval, and flag the gaps that are likely noise.
- **Publishing:** `python -m measures.publish` (from the repo root, `measures/publish.py`) runs
  both and writes `measures/output/success_measures.sqlite`, with a publication record beside it.
- **Reading them back:** the query builder in `mcp/pdp_mcp/results.py` answers a measure, cohort
  and breakdown from the published file, and refuses a file that doesn't match the manifest.

## 3. The API

FastAPI, in `playground/server_application/app/`. Settings are in `app/core/config.py`. Each view
has its own module under `app/sandbox/<view>/`, usually with `routes.py`, `schemas.py` and
`results.py` (the chat, dictionary, pipeline and example modules have no `results.py`).
They get their numbers in one of two ways:

| Where the numbers come from | Modules |
| --- | --- |
| **Published results**, through the query builder (`app/sandbox/results/published.py`) | `deaggregation/`, `course_outcomes/`, `aid_momentum/` (which also runs live queries), and the unfiltered tiles and gaps in `executive_view/published.py` |
| **Counted live** from the data model in the app's database, through read-only aggregate queries (`app/sandbox/chat/query_tool.py`), with groups under 10 hidden | `enrollment_trends/`, `credential_trends/`, `associate_momentum/`, `student_success/`, and the filtered tiles in `executive_view/filtered.py` |
| **Built-in mock fixtures**, no data needed | `chart_examples/`, `kpi_examples/`, `measures/`, `add_a_sandbox_page/` |

The published results are rebuilt by each Workbench run (`pipeline/service.py`, after the tables
load, into the file `published.reader()` reads), or by `python -m measures.publish` from the repo
root. The query builder checks the file's publication record on each query, so a rebuild shows
without a restart.

Other modules: `pipeline/` (uploads, loads and the publish after each), `dictionary/` (column definitions from
`column_dictionary.yaml`) and `chat/` (the AI chat).

## 4. The UI

Next.js, in `playground/client_application/src/`. Each view is a page under
`app/(app)/sandbox/<view>/` (the Workbench and the full-screen dashboard are under `app/(dashboard)/`), and reads its endpoint with types generated from
the API's OpenAPI schema (`mise run web:api-types`). The menus and the landing page come from
`content/sandbox-examples.ts`; the university toggle and themes from `lib/theme.ts`.

## 5. The chat

The chat panel posts a question to `/api/v1/sandbox/chat/suggest` (`app/sandbox/chat/routes.py`). The API
calls the Anthropic API (`app/sandbox/chat/llm.py`) with the instructions in
`.agents/skills/metadata-advisor/SKILL.md` and a few tools: the MCP server's column definitions
(`metadata_tools.py`, `dictionary_tool.py`), the published results (`results_tool.py`) and aggregate
counts (`query_tool.py`), which refuse student-level rows. It needs `ANTHROPIC_API_KEY`; without it
the panel says the chat is off.
