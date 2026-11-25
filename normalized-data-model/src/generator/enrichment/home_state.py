"""Generate the synthetic student home state enrichment file.

The only public API is generate_home_state(). One row per student in the cohort file: the state
the student lived in when they enrolled, as a two-letter code. No value comes from a real
institution.

The real field is State in the PDP cohort submission file (with Zip/Postal Code), which each
college sends to the Clearinghouse but which the Analysis-Ready File leaves out. A college can
export it from its own records and replace this file.

The mock data doesn't say where the college is, so this places it in Illinois: most students are
from Illinois, some from neighboring states, a few from further away. Each student's state is drawn
once with a fixed seed, independent of every outcome on purpose, so a gap by state is noise.

Run from normalized-data-model/:
    python -m src.generator.enrichment.home_state
"""

import argparse
import csv
from pathlib import Path
import random

__all__ = ["generate_home_state"]

_OUTPUT_COLUMNS = ["Student_GUID", "Home_State", "Source"]
_SOURCE = "synthetic: src/generator/enrichment/home_state.py, seed {seed}, independent of outcomes"

# Rough shares for an Illinois community college. Must sum to 1.
_STATE_SHARES = {
    "IL": 0.86,
    "IN": 0.03,
    "WI": 0.025,
    "MO": 0.02,
    "IA": 0.015,
    "MI": 0.01,
    "KY": 0.01,
    "OH": 0.005,
    "TX": 0.005,
    "CA": 0.005,
    "FL": 0.004,
    "NY": 0.004,
    "AZ": 0.002,
    "GA": 0.002,
    "MN": 0.002,
    "CO": 0.001,
}


def generate_home_state(
    cohort_path="../data/raw/pdp_cohort_data.csv",
    output_path="data/input/enrichment/home_state.csv",
    seed=2026,
):
    """Write the home state enrichment file and return the rows written.

    The same seed and cohort file always produce the same file.
    """
    students = _read_students(cohort_path)
    rows = _generate(students, seed)
    _write_rows(rows, output_path)
    return rows


def _read_students(cohort_path):
    """Sorted distinct Student_GUIDs from the cohort file."""
    with open(cohort_path, newline="", encoding="utf-8-sig") as f:
        return sorted({row["Student_GUID"] for row in csv.DictReader(f) if row["Student_GUID"]})


def _generate(students, seed):
    """One row per student, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    states = list(_STATE_SHARES)
    weights = [_STATE_SHARES[s] for s in states]
    source = _SOURCE.format(seed=seed)
    return [
        {"Student_GUID": guid, "Home_State": rng.choices(states, weights=weights)[0], "Source": source}
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
    parser = argparse.ArgumentParser(description="Generate the synthetic student home state enrichment file.")
    parser.add_argument("--cohort", default="../data/raw/pdp_cohort_data.csv", help="cohort Analysis-Ready File")
    parser.add_argument("--output", default="data/input/enrichment/home_state.csv")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    rows = generate_home_state(args.cohort, args.output, args.seed)
    print(f"{len(rows)} students written to {args.output}")


if __name__ == "__main__":
    _main()
