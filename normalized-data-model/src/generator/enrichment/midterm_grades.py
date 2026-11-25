"""Generate the synthetic midterm grades enrichment file.

The only public API is generate_midterm_grades(). One row per course section a student took in the
mock course file, keyed the same way the course file is: Student_GUID, Academic_Year,
Academic_Term, Course_Prefix, Course_Number, Section_ID. Rows with no course (blank prefix) get
no midterm grade. The course file repeats that key on a few hundred rows; they get one row here.

Midterm_Grade is one of:
    A, B, C, D   letter grade at midterm
    L            failing at midterm
    W            withdrew before midterm

It is drawn with a fixed seed, but NOT independently: the weights depend on the course row's
final Grade (_MIDTERM_WEIGHTS), so a strong final grade usually had a strong midterm and a final W
or F usually had an L, D or W. That link is planted by this generator, not found in any data.
Every row's Source says so.

Run from normalized-data-model/:
    python -m src.generator.enrichment.midterm_grades
"""

import argparse
import csv
from pathlib import Path
import random

__all__ = ["generate_midterm_grades"]

_KEY_COLUMNS = ["Student_GUID", "Academic_Year", "Academic_Term", "Course_Prefix", "Course_Number", "Section_ID"]
_OUTPUT_COLUMNS = _KEY_COLUMNS + ["Course_Name", "Midterm_Grade", "Source"]
_SOURCE = "synthetic: src/generator/enrichment/midterm_grades.py, seed {seed}, weighted by the course row's final Grade"
_MIDTERM_GRADES = ("A", "B", "C", "D", "L", "W")

# Weights over _MIDTERM_GRADES for each band of final grade.
_MIDTERM_WEIGHTS = {
    "high": (0.70, 0.25, 0.05, 0.00, 0.00, 0.00),     # final 3.5 to 4.0
    "good": (0.20, 0.55, 0.20, 0.05, 0.00, 0.00),     # final 2.5 to 3.4
    "middle": (0.03, 0.20, 0.50, 0.20, 0.07, 0.00),   # final 1.5 to 2.4
    "low": (0.00, 0.05, 0.25, 0.40, 0.30, 0.00),      # final 0.5 to 1.4
    "failed": (0.00, 0.02, 0.10, 0.33, 0.55, 0.00),   # final F or below 0.5
    "withdrew": (0.00, 0.03, 0.12, 0.20, 0.30, 0.35),  # final W
    "other": (0.25, 0.32, 0.22, 0.10, 0.07, 0.04),    # P, I, blank and other codes: no signal
}


def generate_midterm_grades(
    course_path="../data/raw/pdp_course_data.csv",
    output_path="data/input/enrichment/midterm_grades.csv",
    seed=2026,
):
    """Write the midterm grades enrichment file and return the rows written.

    The same seed and course file always produce the same file.
    """
    sections = _read_sections(course_path)
    rows = _generate(sections, seed)
    _write_rows(rows, output_path)
    return rows


def _band(grade):
    """Which _MIDTERM_WEIGHTS band a final course grade falls in."""
    grade = grade.strip().upper()
    if grade in ("W", "UW"):
        return "withdrew"
    if grade == "F":
        return "failed"
    if grade == "A":  # the mock file uses A on a few rows; read it as a letter A
        return "high"
    try:
        points = float(grade)
    except ValueError:
        return "other"
    if points >= 3.5:
        return "high"
    if points >= 2.5:
        return "good"
    if points >= 1.5:
        return "middle"
    if points >= 0.5:
        return "low"
    return "failed"


def _read_sections(course_path):
    """{key tuple: (course name, final grade)} for each course section, first row wins."""
    sections = {}
    with open(course_path, newline="") as f:
        for row in csv.DictReader(f):
            if not row["Course_Prefix"]:
                continue
            key = tuple(row[c] for c in _KEY_COLUMNS)
            sections.setdefault(key, (row["Course_Name"], row["Grade"]))
    return sections


def _generate(sections, seed):
    """One row per section, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    source = _SOURCE.format(seed=seed)
    rows = []
    for key in sorted(sections):
        name, final = sections[key]
        midterm = rng.choices(_MIDTERM_GRADES, weights=_MIDTERM_WEIGHTS[_band(final)])[0]
        row = dict(zip(_KEY_COLUMNS, key))
        row.update({"Course_Name": name, "Midterm_Grade": midterm, "Source": source})
        rows.append(row)
    return rows


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
    parser = argparse.ArgumentParser(description="Generate the synthetic midterm grades enrichment file.")
    parser.add_argument("--course", default="../data/raw/pdp_course_data.csv", help="course Analysis-Ready File")
    parser.add_argument("--output", default="data/input/enrichment/midterm_grades.csv")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    rows = generate_midterm_grades(args.course, args.output, args.seed)
    students = len({row["Student_GUID"] for row in rows})
    print(f"{len(rows)} course sections for {students} students written to {args.output}")


if __name__ == "__main__":
    _main()
