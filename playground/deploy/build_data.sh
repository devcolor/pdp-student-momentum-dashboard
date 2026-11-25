#!/usr/bin/env bash
# Builds the databases the deployed Playground reads, into server_application/deploy_data/.
# Run from the repo root. Needs requirements.txt installed in $PYTHON (default: python) and uv.
set -euo pipefail

# A full path, so it still works after the steps below change folder.
PYTHON="$(command -v "${PYTHON:-python}")"
case "$PYTHON" in /*) ;; *) PYTHON="$PWD/$PYTHON" ;; esac
OUT=playground/server_application/deploy_data
FULL_MEASURES=measures/output/success_measures.sqlite
mkdir -p "$OUT"

echo "1. Load the raw CSVs into the data model"
(cd normalized-data-model && "$PYTHON" -m src.pipeline.run)

echo "2. Add the Playground's own tables, on a copy of the model"
cp normalized-data-model/output/pdp.sqlite "$OUT/playground.sqlite"
(cd playground/server_application &&
  DATABASE_URL=sqlite:///deploy_data/playground.sqlite uv run --no-dev alembic upgrade head)

echo "3. Publish the shared measures and gaps that measures/manifest.yaml approves, in one run"
PYTHONPATH=. "$PYTHON" -m measures.publish

echo "4. Trim the measures copy to fit Vercel (with its own publication record), and check the pages on the query builder don't change"
"$PYTHON" playground/deploy/trim_measures.py "$FULL_MEASURES" "$OUT/success_measures.sqlite"
(cd playground/server_application &&
  PYTHONPATH=. uv run --no-dev python ../deploy/check_pages.py "../../$FULL_MEASURES" deploy_data/success_measures.sqlite)

ls -lh "$OUT"
