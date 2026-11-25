"""Generate the synthetic student affinity enrichment file.

The only public API is generate_affinity(). One row per student in the cohort file: the
extracurricular group the student belongs to (Band, Football, ... or None). No value comes from a
real institution.

Each student's affinity is drawn once with a fixed seed from _AFFINITY_SHARES, independent of
every outcome on purpose. A chart that splits Retention by affinity should come out flat, and
any gap it shows is noise. Every row's Source says so.

Run from normalized-data-model/:
    python -m src.generator.enrichment.affinity
"""

import argparse
import csv
from pathlib import Path
import random

__all__ = ["generate_affinity"]

_OUTPUT_COLUMNS = ["Student_GUID", "Affinity", "Source"]
_SOURCE = "synthetic: src/generator/enrichment/affinity.py, seed {seed}, independent of outcomes"

# Rough shares for a community college: most students join nothing. Must sum to 1.
_AFFINITY_SHARES = {
    "None": 0.62,
    "Band": 0.05,
    "Choir": 0.04,
    "Theater": 0.03,
    "Football": 0.05,
    "Baseball": 0.04,
    "Basketball": 0.04,
    "Volleyball": 0.03,
    "Soccer": 0.04,
    "Student Government": 0.02,
    "Esports": 0.04,
}


def generate_affinity(
    cohort_path="../data/raw/pdp_cohort_data.csv",
    output_path="data/input/enrichment/affinity.csv",
    seed=2026,
):
    """Write the affinity enrichment file and return the rows written.

    The same seed and cohort file always produce the same file.
    """
    students = _read_students(cohort_path)
    rows = _generate(students, seed)
    _write_rows(rows, output_path)
    return rows


def _read_students(cohort_path):
    """Sorted distinct Student_GUIDs from the cohort file."""
    with open(cohort_path, newline="") as f:
        return sorted({row["Student_GUID"] for row in csv.DictReader(f) if row["Student_GUID"]})


def _generate(students, seed):
    """One row per student, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    names = list(_AFFINITY_SHARES)
    weights = [_AFFINITY_SHARES[n] for n in names]
    source = _SOURCE.format(seed=seed)
    return [
        {"Student_GUID": guid, "Affinity": rng.choices(names, weights=weights)[0], "Source": source}
        for guid in students
    ]


def _write_rows(rows, output_path):
    """Write rows as CSV, creating the folder if needed."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _main(argv=None):
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Generate the synthetic student affinity enrichment file.")
    parser.add_argument("--cohort", default="../data/raw/pdp_cohort_data.csv", help="cohort Analysis-Ready File")
    parser.add_argument("--output", default="data/input/enrichment/affinity.csv")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    rows = generate_affinity(args.cohort, args.output, args.seed)
    print(f"{len(rows)} students written to {args.output}")


if __name__ == "__main__":
    _main()
