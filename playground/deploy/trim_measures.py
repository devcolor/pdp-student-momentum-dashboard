"""Copy the measures file without its hidden course rows, so the API fits Vercel's 500 MB limit.

Usage: python trim_measures.py <full success_measures.sqlite> <copy to write>

The full file must be published (python -m measures.publish) from measures/manifest.yaml, so it has
a publication record beside it that matches. The query builder (mcp/pdp_mcp/results.py) checks that
before the copy is made, and checks the copy's own record after: the same manifest and load, with
the copy's checksum. Dropping hidden rows reveals nothing: a hidden row has no numbers, and a
missing group reads the same on every page that reads the copy (check_pages.py).
"""

import json
import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "mcp"))

from pdp_mcp.results import ResultsReader, SpecRefused, file_sha256, publication_path  # noqa: E402

# Hidden course rows have no rate. The course outcomes page shows a missing row the same way.
DROP_HIDDEN_COURSE_ROWS = """
DELETE FROM success_measures
WHERE status = 'suppressed' AND group_dimensions LIKE 'course%'
"""


def check(manifest: Path, results: Path) -> dict:
    """The file's publication record, or exit with the query builder's reason for refusing it."""
    try:
        return ResultsReader(manifest, results).check_publication()
    except SpecRefused as error:
        sys.exit(f"{results}: {error}")


def trim(source: Path, target: Path, manifest: Path = REPO / "measures/manifest.yaml") -> None:
    """Write the trimmed copy and its publication record, and say how much smaller it is."""
    record = check(manifest, source)

    shutil.copyfile(source, target)
    connection = sqlite3.connect(target)
    try:
        dropped = connection.execute(DROP_HIDDEN_COURSE_ROWS).rowcount
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    trimmed = {
        **record,
        "results_sha256": file_sha256(target),
        "trimmed_from_sha256": record["results_sha256"],
        "trimmed": "hidden course rows dropped to fit Vercel",
    }
    publication_path(target).write_text(json.dumps(trimmed, indent=2) + "\n", encoding="utf-8")
    # The deploy reads the copy, so it must pass the same check the full file did.
    check(manifest, target)
    before, after = source.stat().st_size // 1_000_000, target.stat().st_size // 1_000_000
    print(f"Dropped {dropped} hidden course rows: {before} MB to {after} MB")


if __name__ == "__main__":
    trim(Path(sys.argv[1]), Path(sys.argv[2]))
