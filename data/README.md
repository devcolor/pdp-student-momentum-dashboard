# Data

The data in this folder is **synthetic mock data**. It was made by
[Achieving the Dream](https://achievingthedream.org/) in the shape of the Postsecondary Data
Partnership (PDP) analysis-ready files. **There are no real students in it.** Nothing built on it
is a finding about real students or a real institution.

## What's here

| Path | What it is |
| --- | --- |
| `raw/pdp_cohort_data.csv` | The cohort file: one row per student per cohort. 10,313 rows and 85 columns |
| `raw/pdp_course_data.csv` | The course file: one row per student per course per term. 100,951 rows and 35 columns |
| [manifest.json](manifest.json) | Each raw file's checksum, row count and column names. `python scripts/check.py` fails if a file doesn't match |
| [dictionaries/](dictionaries/) | The PDP data dictionaries for the cohort, course and financial aid files, and `column_lookup.csv`, which maps each shortened CSV column to its dictionary name |
| [quality/](quality/README.md) | The log of known issues in the mock files, and a script that recounts them |

Row counts don't include the header. The files have no newline after the last row, so `wc -l`
misses the last line and prints the row count itself; subtracting the header gives one too few.
Count rows with a CSV reader, as `scripts/check.py` does.

The financial aid file isn't included; only its dictionary is. The financial aid, housing and other
enrichment files the data model loads are made up too, by generators with fixed seeds: see
[the data model's README](../normalized-data-model/README.md).

Don't re-save, sort, re-encode or change the line endings of the raw files. They use Windows (CRLF)
line endings, and any byte change breaks the checksum in `manifest.json`.

## Replacing the files with a real PDP export

> [!CAUTION]
> **FERPA.** A real PDP export holds education records protected by the Family Educational Rights
> and Privacy Act. **Never commit one,** to any repository, public or private, and never paste one
> into an AI tool your institution hasn't approved.

1. Download your institution's cohort and course analysis-ready files from PDP, and name them
   `pdp_cohort_data.csv` and `pdp_course_data.csv`.
2. Put them in `data/private/`. That folder is in the repo's `.gitignore`, so git won't pick them
   up. If you keep them anywhere else in the repo, add that path to `.gitignore` first. The two
   files in `raw/` are tracked, so `.gitignore` can't protect them: if you overwrite them, never
   commit or push.
3. Load them with the data model's loader (`--cohort` and `--course` take their paths) or upload
   them in the app's Workbench. The steps, including the enrichment files and mock-data fixes to
   change, are in the README's
   [Swapping in your own PDP files](../README.md#swapping-in-your-own-pdp-files).
4. If you did overwrite the files in `raw/`, run `python scripts/check.py --update` to rewrite
   `manifest.json`, and update the table in the README to the new counts. Treat the new manifest
   as private too: it records your files' column names and row counts.

Check your export's column names against `dictionaries/column_lookup.csv`. A real export may name
or order columns differently from the mock files, and the Workbench's upload stops on a column it
doesn't expect.

## Terms

The mock data, the data dictionaries and the column lookup are Achieving the Dream's, provided for
the PDP. They are **not** covered by this repository's [MIT License](../LICENSE). Ask Achieving the
Dream before reusing them outside this project.
