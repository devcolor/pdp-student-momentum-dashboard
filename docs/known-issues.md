# Known issues

This project is released as-is and isn't maintained, so these won't be fixed here. The data is
synthetic: nothing here is a finding about real students or institutions.

## Mock data quirks

The full, counted list is [data/quality/findings.csv](../data/quality/findings.csv), and
`python data/quality/run_checks.py` recounts it. The ones you're most likely to notice:

- **Two students are in two cohorts each,** so the cohort file has 10,313 rows but 10,311
  students. The data model keeps one `student` row each and the later cohort's values.
- **Course years run wider than the cohorts:** 2012-13 to 2026-27, against cohorts from 2021-22
  to 2024-25. 456 course rows have no year.
- **Blanks and codes for "unknown" are mixed:** blanks, `.`, `UK`, `-1`, `NA` and `MISSING` all
  appear, and don't always mean the same thing. Read the CSVs as text.
- **`Grade` is text,** with codes the dictionary doesn't list (`OTH`, `UW`, `MIS` and others), and
  17.6% of course rows have none.
- **Numbers that lost digits:** program and CIP codes lost their leading zeros, and `Section_ID` is
  in scientific notation.
- **No institution column,** so the files are treated as one institution's extract.
- **No financial aid file.** Only its dictionary is included. The financial aid the app shows is
  generated.

`normalized-data-model/config/data_fixes.yaml` fixes the ones that would break a load. A real PDP
export may not have these bugs, so check that file before loading one.

## Synthetic enrichment data

The files in `normalized-data-model/data/input/enrichment/` are made up, with fixed seeds, except `institution_events.csv`, a list of public events. Some have
effects built in on purpose, so their results show only that the code works:

- **Financial aid** (unmet need band) has a planted link with retention.
- **Midterm grades** are generated from the final grades, so any link between midterm alerts and
  DFW rates is circular.
- **Age and per-term Pell** in the student matrix follow the mock data's own groups, so they carry
  its existing gaps.
- **Affinity, home state, educational goal and promise status** are independent of every outcome:
  any gap by them is noise.

Each generator's docstring, in `normalized-data-model/src/generator/enrichment/`, says what's
planted. None of these files match a real institution's students.

## Local-only features

- **Uploads and loads persist only when the app runs locally.** They're saved under
  `normalized-data-model/data/uploads/` and in the app's SQLite file. On a serverless or demo
  deploy the disk is read-only or reset, so the Workbench's Upload and **Use the mock files** don't
  work or don't last there.
- **Each load replaces the data model's tables.** Rows added to those tables by hand are lost on
  the next load.
- **The Sandbox and Workbench are off in production** (`APP_ENV=production`) unless
  `SANDBOX_ENABLED=true` is set as a real environment variable. [Host it yourself](self-hosting.md)
  uses that, so the Swagger page stays hidden. The Vercel example runs as `staging` instead.
- **There's no login.** Anyone who can reach the app can upload, load, delete and read, and
  `GET /api/v1/sandbox/pipeline/tables/{name}` returns student-level rows. Put the app behind your
  sign-on before loading real data: see [Host it yourself](self-hosting.md).

## The AI chat and your API key

- **The chat needs your own Anthropic key** (`ANTHROPIC_API_KEY`). Without one, the chat panel
  says the chat is off and how to turn it on, and every other page works.
- **On a public site, anyone with the link can spend the key.** Leave it unset there, or set a
  spending limit in the Anthropic console. `SANDBOX_CHAT_ENABLED=false` turns the chat off without
  removing the key.
- **The chat sends aggregate counts and column definitions to Anthropic,** never student-level
  rows; its checks refuse rows that look like individual students. Those checks catch mistakes;
  they aren't a security boundary. With a real export, get your institution's approval before
  turning the chat on.
- **Answers can be wrong.** It's a language model: check a number against its view before using it.
- **Two kinds of tile figure can't be checked by the chat.** Every KPI tile's value and trend arrow is
  published, and a test checks the chat's `query_results` gives the same, with two exceptions.
  The executive view's graduation rate comes from the institution's records, not PDP, so it is never
  published. A completion value shown "so far" (a cohort still inside its 3-year window) is
  published as not yet observable. The chat says it can't confirm either. On All cohorts, the
  completion tile pools only 2021-22 and 2022-23; the chat checks it from those two published rows.

## Untested or lightly tested paths

- **Windows.** The mise tasks are bash scripts. The Playground's README shows how to point mise at
  Git Bash, but the full quick start hasn't been run on Windows.
- **PostgreSQL vs SQLite.** The quick start and the Playground's CI use SQLite. PostgreSQL needs
  Docker (`mise run db:choose postgresql`, then `mise run db`), and the views' live queries,
  vector search and migrations have had less testing on it.
- **Real PDP exports.** Everything was built and tested on the mock files. A real export may name
  columns differently, and many of the foundations' tests assume the mock data.
- **Python 3.15.** `pip install -r requirements.txt` fails on it (no pyarrow wheel yet). Use the
  Python 3.14 that mise installs, as the quick start does.
- **Hosting.** Only the Vercel example in `playground/deploy/` has been tried, and it needs the
  measures file trimmed to fit Vercel's size limit.

## Other things to know

- **The published measures file is large,** about 650 MB, mostly hidden rows for small course
  groups. A Workbench run rebuilds it after each load; after changing the data any other way,
  rerun `python -m measures.publish`, or the views show the old results. No restart is needed.
- **A Workbench run only publishes the manifest's cohort years** (2021-22 to 2024-25, fixed in
  `measures/manifest.yaml`). An upload missing one still loads its tables, but the publish fails,
  names the missing year, and the published views keep the earlier results.
- **Views that read published results** (de-aggregation, course outcomes, unmet need, the
  executive view's gaps) show nothing until `python -m measures.publish` or a Workbench run has
  published. Views that count live show a "load the data model" message until the mock data is
  loaded.
- **A Next.js upgrade notice can stop the first `mise run web:dev` or `mise run web:build`,**
  including in CI, whenever a new advisory affects the pinned version. Run the command again and
  it continues. This release pins Next 16.4.6, which the npm registry reported as advisory-free on
  24 November 2026. Check for newer ones and upgrade before deploying anywhere public.
- **The landing page links to a source repository** set by `NEXT_PUBLIC_REPOSITORY_URL`. Set it
  to your copy.
- **Small-group hiding is display protection, not a guarantee.** Groups under 10 students are
  hidden, and a second group is hidden where the first could be worked out by subtraction. See the
  Rules in [measures/README.md](../measures/README.md). It has only been checked against the mock
  data, so a rebuild from an uploaded file is protected only as far as those rules go.
