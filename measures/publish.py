"""Publishes the approved results. Run from the repo root, after loading the data: python -m measures.publish

Each measure and cohort in manifest.yaml is run once, with every breakdown approved for it, and the gap
finder compares the groups of that same run. A measure with single cohorts is
run once for its pooled cohort and every single year together, so hiding also checks the pool against its
years; only the breakdowns approved for the single years are kept for them. One run hides one set of
groups, so rows from different runs can't be set against each other, and success_measures and
equity_gaps hide the same groups. Within the run, hiding has the limits listed under Rules in
README.md: display protection, not a guarantee.

The results file is written fresh each time, so it holds what the manifest approves and nothing older.
Version 7 adds measure_trends: each single cohort's change from the one before, for every shown group,
worded as the tiles word it (measures/compare.py), plus the entering students' change.

A publication record beside it holds the manifest's version and both files' checksums, so the query
builder (mcp/pdp_mcp/results.py) can refuse a results file that doesn't match the manifest it reads.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
from pathlib import Path

from .compare import CohortTrend, compare, compare_values
from .manifest import MANIFEST, Manifest, load_manifest
from .models import EVERYONE, MAKE_UP_MEASURES, Cohort, GroupDimension, Measure, MeasureResult, Status
from .run_measures import latest_load, open_database, read_sources, run_measure
from .save_results import RESULTS_DATABASE, save_results, save_trends

logger = logging.getLogger(__name__)

# Breakdowns whose rates are published but whose gaps aren't tested. Both are synthetic and independent of
# every outcome, except educational_goal UNKNOWN (no fall term), which differs by construction: any other
# difference is noise. Leaving them out also keeps the published equity_gaps as before.
UNTESTED_DIMENSIONS = frozenset({GroupDimension.AFFINITY, GroupDimension.EDUCATIONAL_GOAL})

# Measures whose rates are published but that get no gaps: cohort make-up says who entered, so a group
# "behind" on it is no shortfall.
NO_GAPS = MAKE_UP_MEASURES

# The KPI name of the entering students trend, read from a make-up measure's everyone denominators.
ENTERING_STUDENTS = "entering_students"

# Every table the measure calculations read. A database missing one was loaded before that table
# existed, so it is checked up front rather than failing part way through a run that takes minutes.
MEASURE_TABLES = frozenset({
    "cohort_membership",
    "course",
    "course_enrollment",
    "midterm_grade",
    "student",
    "student_attribute",
    "student_term_matrix",
    "term",
})


# mcp/pdp_mcp/results.py reads the record with its own copy of these two helpers (it imports nothing
# from measures/), so a change to the name or the checksum here must be made there too.
def publication_path(results: Path) -> Path:
    """Where the publication record for a results file goes, e.g. success_measures.publication.json."""
    return results.with_name(f"{results.stem}.publication.json")


def publish(database=None, results: Path = RESULTS_DATABASE, manifest_path: Path = MANIFEST) -> dict:
    """Write every approved measure, cohort and breakdown, and their gaps, to a fresh results file.

    database is the loaded SQLite file or an open connection, as for run_measure. Returns the record.
    """
    # The gap finder runs the measures itself, so it's imported here rather than at the top: measures
    # stays usable without it, and the import can't go in a circle.
    from gap_finder.compare import compare as compare_groups
    from gap_finder.save_results import save_gaps
    from gap_finder.sources import NOT_YES_OR_NO, check_cohorts_have_students, to_count_row

    manifest = load_manifest(manifest_path)
    building = results.with_name(f"{results.stem}.building{results.suffix}")
    building.unlink(missing_ok=True)

    connection, opened_here = open_database(database)
    try:
        try:
            check_model_has_measure_tables(connection)
            check_cohorts_have_students(connection, [*manifest.cohorts, *manifest.single_cohorts])
            loaded_at = latest_load(read_sources(connection))
            trends: list[CohortTrend] = []
            for measure, group_by in manifest.breakdowns.items():
                for cohorts in manifest.runs(measure):
                    rows = run_measure(measure, cohorts, list(group_by), database=connection)
                    # Single cohorts are run with every breakdown the pool has, so their hiding is checked
                    # against the pool's; only the ones the manifest approves for them are kept.
                    rows = [row for row in rows if manifest.approves(measure, row.cohort, row.group)]
                    save_results(rows, loaded_at, building)
                    if measure not in NOT_YES_OR_NO and measure not in NO_GAPS:
                        tested = [row for row in rows if not uses_untested_dimension(row)]
                        save_gaps(compare_groups([to_count_row(row, loaded_at) for row in tested]), building)
                    trends += trend_rows(measure, rows, manifest)
                    # Every make-up measure's denominators are the entering students: one is enough.
                    if measure in MAKE_UP_MEASURES and not any(t.kpi == ENTERING_STUDENTS for t in trends):
                        trends += entering_trend_rows(rows, manifest)
                    labels = ", ".join(cohort.label for cohort in cohorts)
                    logger.info("%s, %s: published %d rows", measure.value, labels, len(rows))
            save_trends(trends, building)
        finally:
            if opened_here:
                connection.close()
        record = {
            "manifest_version": manifest.version,
            "manifest_sha256": manifest.sha256,
            "results_sha256": file_sha256(building),
            "data_loaded_at": loaded_at,
        }
        record_path = publication_path(results)
        pending_record = record_path.with_name(f"{record_path.name}.building")
        pending_record.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        # A failed run leaves the last good results and record, and nothing half built beside them.
        building.unlink(missing_ok=True)
        raise

    # Swap the results and then the record straight after, so a reader sees the new file without
    # its record only for that instant, rather than for as long as hashing takes.
    os.replace(building, results)
    os.replace(pending_record, record_path)
    return record


def neighbouring_years(manifest: Manifest) -> list[tuple[Cohort, Cohort]]:
    """Each single cohort with the one before it, oldest first, e.g. (2021-22, 2022-23)."""
    singles = sorted(manifest.single_cohorts, key=lambda cohort: cohort.label)
    return list(zip(singles, singles[1:]))


def trend_rows(measure: Measure, rows: list[MeasureResult], manifest: Manifest) -> list[CohortTrend]:
    """Each single-cohort group's change from the year before, read by compare() as every tile reads it.

    Only when both years' rows are shown: compare() gives nothing for a hidden one. None for a pool, and
    none for a year the manifest's no_trend lists for the measure.
    """
    by_key = {(row.cohort, row.group): row for row in rows}
    groups = sorted({row.group for row in rows if row.cohort in manifest.single_cohorts}, key=lambda g: g.label)
    skipped = manifest.no_trend.get(measure, frozenset())
    trends = []
    for earlier, latest in neighbouring_years(manifest):
        if latest.label in skipped:
            continue
        for group in groups:
            before, now = by_key.get((earlier, group)), by_key.get((latest, group))
            if before is None or now is None:
                continue
            change = compare(before, now)
            if change is not None:
                trends.append(CohortTrend(measure.value, latest.label, earlier.label, group, change))
    return trends


def entering_trend_rows(rows: list[MeasureResult], manifest: Manifest) -> list[CohortTrend]:
    """The entering students' change from the year before, from a make-up measure's everyone denominators."""
    everyone = {row.cohort: row for row in rows if row.group == EVERYONE}
    trends = []
    for earlier, latest in neighbouring_years(manifest):
        before, now = everyone.get(earlier), everyone.get(latest)
        if before is None or now is None or before.status != Status.OK or now.status != Status.OK:
            continue
        change = compare_values(ENTERING_STUDENTS, float(before.denominator), float(now.denominator))
        if change is not None:
            trends.append(CohortTrend(ENTERING_STUDENTS, latest.label, earlier.label, EVERYONE, change))
    return trends


def check_model_has_measure_tables(connection) -> None:
    """Refuse a data model loaded before a table the measures need, which is a stale load.

    Without this the run gets part way and stops on `no such table`, and the advice everything
    else gives ("publish the results") is the command that just failed.
    """
    cursor = connection.cursor()
    if isinstance(connection, sqlite3.Connection):
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        loaded = {row[0] for row in cursor.fetchall()}
    else:
        # PostgreSQL: a table counts if its unqualified name resolves on search_path, as the measures' SQL does.
        loaded = set()
        for table in MEASURE_TABLES:
            cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (table,))
            if cursor.fetchone()[0]:
                loaded.add(table)
    missing = sorted(MEASURE_TABLES - loaded)
    if missing:
        raise ValueError(
            f"the loaded data model has no {', '.join(missing)}: it was loaded before "
            f"{'that table' if len(missing) == 1 else 'those tables'} existed. Load it again "
            f"(cd normalized-data-model && python -m src.pipeline.run), then publish."
        )


def uses_untested_dimension(row: MeasureResult) -> bool:
    """Whether the row's group uses a dimension whose gaps aren't tested."""
    return any(part.dimension in UNTESTED_DIMENSIONS for part in row.group.parts)


def file_sha256(path: Path) -> str:
    """The file's SHA-256, read in chunks: the results file can be hundreds of megabytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    published = publish()
    print(f"Published manifest version {published['manifest_version']} to {RESULTS_DATABASE}.")
