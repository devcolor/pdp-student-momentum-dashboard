# AGENTS.md

Instructions for AI coding agents working in this repo. People can read it too.

This repo holds the mock data, the shared foundations and the SYMPA Playground app. See
[README.md](README.md) for what it does and how to run it.

## Before prompting

- **Plan first.** For anything bigger than a small fix, use a planning skill before writing code.
- **Don't write code on `main`.** Work on a branch.
- **Run steps in parallel when you can.** For each step, ask whether it really needs the previous
  step's result. If it doesn't, run it in parallel.
- **Start simple.** Build the plain version first. Split work up only after you see where it's
  slow.

## While building

- **Define the check first.** Before building, write down how you'll know it works: a command, a
  test, or an expected number.
- **Cap every retry loop.** Give each fix-and-retry loop a maximum number of tries (3 is a good
  default). At the cap, stop and ask a person. Don't keep trying.
- **Run the checks.** Use `make check-fast` while you work and `make check` before opening a pull
  request. If you changed `playground/`, also run the Playground's commands, because `make check`
  doesn't cover them. The README's [Run the tests](README.md#run-the-tests) section says what to
  run and what each error means. On Windows, run the commands listed there.
  CI runs all of it on every pull request, and it must pass to merge. Install `requirements.txt`
  into `.venv/` first, and again whenever it changes: `python -m pip install -r requirements.txt`.

## Code and comments

- Every method and class gets a short one-line comment saying what it does.
- Other comments are short, plain and only where needed. No walls of text.
- Don't comment what the code already says. Comment the why, or a rule that isn't obvious.
- Write code a teammate can read at a glance. No clever tricks or dense one-liners.

## Repo rules

- **The data is synthetic.** Nothing built on it is a finding about real students or
  institutions. Say so whenever you report a result.
- **Use the `pdp-data` skill for raw ARF data questions** ([.agents/skills/pdp-data/SKILL.md](.agents/skills/pdp-data/SKILL.md)).
  CSV column names are shortened; look them up in `data/dictionaries/column_lookup.csv` instead
  of guessing.
- **For comparing groups or finding gaps, use the gap finder:** `find_gaps` or the `equity_gaps`
  table ([gap_finder/README.md](gap_finder/README.md)). Don't recompute gaps from `data/raw/`.
- **Use `pdp-sandbox`** when building a Playground Sandbox endpoint or chart from the normalized
  PDP data model ([.agents/skills/pdp-sandbox/SKILL.md](.agents/skills/pdp-sandbox/SKILL.md)).
- **For Playground UI and stories,** follow
  [the client agent instructions](playground/client_application/AGENTS.md), including the Storybook
  MCP guidance and source-file fallback.
- **Python packages go in `requirements.txt`,** pinned to exact versions (`package==1.2.3`) with
  a comment naming the foundation that needs them. Packages only a notebook needs go in
  `notebooks/requirements.txt`, which CI doesn't install. Install them in a virtual environment
  (`.venv/`), never into the system Python. Target Python 3.10 or newer. Keep
  `scripts/check.py` standard-library only.
- **Never rewrite or reformat files in `data/raw/` as a side effect.** Don't re-save, sort,
  re-encode, or change the line endings of the CSVs. They use Windows (CRLF) line endings, and any byte change breaks the
  checksum in `data/manifest.json`. Read them; write results somewhere else.
- **Never commit generated outputs,** such as DuckDB or SQLite databases, Parquet files, or
  exported CSVs. Commit the code that makes them, and add the output path to `.gitignore`.
  - **Exception:** the data model in `normalized-data-model/` commits the generated files listed
    below. Each is an input or a test fixture, not the result of a run: committing it means every
    clone loads and tests against the same file. Regenerate them with the commands in
    `normalized-data-model/README.md`; don't edit them by hand.
    - `normalized-data-model/data/input/enrichment/on_campus_housing.csv`: the synthetic
      on-campus housing input, made with a fixed seed.
    - `normalized-data-model/data/input/enrichment/financial_aid.csv`: the synthetic financial aid
      input, made with a fixed seed and a declared planted effect. The real financial aid
      Analysis-Ready File is not in this repo, so this stands in for it. Its relationship with
      Retention is deliberate and is named in every row's `Source` column: read the generator's
      docstring before reporting anything measured by unmet need band.
    - `normalized-data-model/data/input/enrichment/student_matrix.csv`: the synthetic student
      matrix input (about 6 MB), made with a fixed seed. One row per student per fall, with every
      column an institution's student matrix export has and PDP doesn't. Most columns are derived
      from the mock cohort and course files; educational goal, promise status, age and per-term Pell
      are random draws. Only educational goal and promise status are independent of every outcome.
      Age is drawn inside the student's PDP age band and Pell leans on Pell_Status_First_Year, so
      both inherit the mock data's existing gaps. The generator's docstring says which is which.
    - `normalized-data-model/data/input/enrichment/affinity.csv`: each student's synthetic
      extracurricular group, made with a fixed seed and independent of every outcome.
    - `normalized-data-model/data/input/enrichment/home_state.csv`: each student's synthetic home
      state, made with a fixed seed and independent of every outcome. It stands in for State in the
      PDP cohort submission file, which the Analysis-Ready File leaves out; the mock college is
      placed in Illinois.
    - `normalized-data-model/data/input/enrichment/all_students_extras.csv`: the built-in synthetic
      supplemental sample, made with a fixed seed and independent of every outcome: each student's
      state and affinity group (copied from home_state.csv and affinity.csv, under their own names),
      home ZIP (inside that state), number of siblings and dietary restriction. It's
      in the long shape a Workbench supplemental upload is loaded in, so the Executive view's
      Supplemental data card has a file to show without an upload, including on the deployed site.
    - `normalized-data-model/data/input/enrichment/midterm_grades.csv`: a synthetic midterm grade
      for each course section (about 16 MB), made with a fixed seed. It's weighted by the course
      row's final grade on purpose, so midterm and final grades agree because the generator says
      so, not because of any data. Each row's `Source` declares it.
    - `normalized-data-model/data/input/sample/` and `normalized-data-model/data/output/sample/`:
      the raw rows and the tables for 10 sample students (about 70 KB). The tests compare a
      rebuild against them, and you can open them without running anything.
    - `normalized-data-model/config/column_dictionary.yaml`: what each normalized column means,
      built from `data/dictionaries/arf_*_data_dictionary.md` and `column_lookup.csv`. Edit those
      files, not this one: `tests/dictionary/test_build.py` fails if it differs from a rebuild.
  - **Exception:** `mcp/schemas/tools.json`, the MCP server's published tool contract. It's the
    server's `tools/list`, written by `python -m pdp_mcp.export_schemas` (run from `mcp/`), so
    tools in any stack can read the schemas without running Python. Don't edit
    it by hand: `mcp/tests/test_contracts.py` fails if it differs from the running server. This
    exception covers that one file only.
- **Data changes must be deliberate.** If you change anything in `data/raw/` on purpose, run
  `python scripts/check.py --update`, update the README data table, and commit both in the same
  pull request.
- **Before you finish a change,** make sure `make check` passes, and if you add something
  others will use, explain it in the README.

## Agent skills

The skill sets in `.agents/skills/` and `.claude/skills/` are committed and ready to use. The
`.compound-engineering/` folder is ignored by git: this repo sets no config there, so don't commit
one.

### Issue tracker

This release doesn't take issues or pull requests. A fork that tracks its own work can use GitHub
Issues with the `gh` CLI; see [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md).

### Triage labels

`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See
[docs/agents/triage-labels.md](docs/agents/triage-labels.md).
