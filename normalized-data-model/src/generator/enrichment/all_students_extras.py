"""Generate the built-in synthetic supplemental sample: extra data for every student.

The only public API is generate_all_students_extras(). It stands in for a file an institution would
upload in the Workbench where the PDP files fall short, so the Executive view's Supplemental data
card has something to show without an upload, including on the deployed site, which can't save.

Five values per student, independent of every outcome on purpose:
    State                 copied from home_state.csv, the student's synthetic home state
    Home_Zip              drawn inside that state's ZIP range, so the two agree
    Affinity_Group        copied from affinity.csv, the student's synthetic extracurricular group
    Number_Of_Siblings    drawn: 0 to 5, one being most common
    Dietary_Restriction   drawn: one of None, Vegetarian, Vegan, Halal, Gluten-free
State and Affinity_Group get their own names, not home_state and affinity, so the map and the
affinity filter, which read those, don't see each student twice. The drawn values use a fixed seed.

The file is in the long shape config/supplemental_mapping.yaml loads into student_attribute, the
same as a Workbench upload, with a Source saying it's the built-in sample. Its wide twin, the shape
an institution would upload, is what the generator draws first: one row per student.

Run from normalized-data-model/, after home_state.csv and affinity.csv exist:
    python -m src.generator.enrichment.all_students_extras
"""

import argparse
import csv
from pathlib import Path
import random

__all__ = ["generate_all_students_extras"]

_OUTPUT_COLUMNS = ["Student_GUID", "Academic_Year", "Academic_Term", "Attribute_Key", "Attribute_Value", "Source"]
_SOURCE = "supplemental: all_students_extras.csv (built-in synthetic sample, seed {seed})"

# The first three ZIP digits each home state uses, low to high.
_ZIP_PREFIXES = {
    "IL": (600, 629), "IN": (460, 479), "WI": (530, 549), "MO": (630, 658), "IA": (500, 528),
    "MI": (480, 499), "KY": (400, 427), "OH": (430, 458), "TX": (750, 799), "CA": (900, 961),
    "FL": (320, 349), "NY": (100, 149), "AZ": (850, 865), "GA": (300, 319), "MN": (550, 567),
    "CO": (800, 816),
}
# The value columns, in file order; each is an attribute named after it in lower case.
_VALUE_COLUMNS = ["State", "Home_Zip", "Affinity_Group", "Number_Of_Siblings", "Dietary_Restriction"]
_SIBLINGS = [0, 1, 2, 3, 4, 5]
_SIBLING_WEIGHTS = [0.18, 0.34, 0.26, 0.12, 0.06, 0.04]
_DIETS = ["None", "Vegetarian", "Vegan", "Halal", "Gluten-free"]
_DIET_WEIGHTS = [0.70, 0.12, 0.05, 0.08, 0.05]


def generate_all_students_extras(
    cohort_path="../data/raw/pdp_cohort_data.csv",
    home_state_path="data/input/enrichment/home_state.csv",
    affinity_path="data/input/enrichment/affinity.csv",
    output_path="data/input/enrichment/all_students_extras.csv",
    seed=2026,
):
    """Write the long-shape sample file and return its wide rows, one per student.

    The same seed, cohort file, home states and affinity groups always produce the same file.
    """
    students = _read_students(cohort_path)
    home = _read_column(home_state_path, "Home_State")
    affinity = _read_column(affinity_path, "Affinity")
    wide = _generate(students, home, affinity, seed)
    _write_long(wide, output_path, _SOURCE.format(seed=seed))
    return wide


def _read_students(cohort_path):
    """Sorted distinct Student_GUIDs from the cohort file."""
    with open(cohort_path, newline="", encoding="utf-8-sig") as f:
        return sorted({row["Student_GUID"] for row in csv.DictReader(f) if row["Student_GUID"]})


def _read_column(path, column):
    """Each student's value of one column of another enrichment file, such as home_state.csv."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {row["Student_GUID"]: row[column] for row in csv.DictReader(f)}


def _generate(students, home, affinity, seed):
    """One wide row per student. Same seed, same rows. A student with no home state counts as IL."""
    rng = random.Random(seed)
    rows = []
    for guid in students:
        state = home.get(guid, "IL")
        low, high = _ZIP_PREFIXES[state]
        zip_code = f"{rng.randint(low, high):03d}{rng.randint(0, 99):02d}"
        rows.append({
            "Student_GUID": guid,
            "State": state,
            "Home_Zip": zip_code,
            "Affinity_Group": affinity.get(guid, "None"),
            "Number_Of_Siblings": str(rng.choices(_SIBLINGS, _SIBLING_WEIGHTS)[0]),
            "Dietary_Restriction": rng.choices(_DIETS, _DIET_WEIGHTS)[0],
        })
    return rows


def _write_long(wide, output_path, source):
    """Write each wide row as three long rows, in column order, creating the folder if needed."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(_OUTPUT_COLUMNS)
        for row in wide:
            for column in _VALUE_COLUMNS:
                writer.writerow([row["Student_GUID"], "", "", column.lower(), row[column], source])


def _main(argv=None):
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description="Generate the built-in synthetic supplemental sample.")
    parser.add_argument("--cohort", default="../data/raw/pdp_cohort_data.csv", help="cohort Analysis-Ready File")
    parser.add_argument("--home-states", default="data/input/enrichment/home_state.csv")
    parser.add_argument("--affinity", default="data/input/enrichment/affinity.csv")
    parser.add_argument("--output", default="data/input/enrichment/all_students_extras.csv")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    rows = generate_all_students_extras(args.cohort, args.home_states, args.affinity, args.output, args.seed)
    print(f"{len(rows)} students written to {args.output}")


if __name__ == "__main__":
    _main()
