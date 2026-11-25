"""Generate the synthetic financial aid enrichment file.

The only public API is generate_financial_aid(). One row per student per academic year, from
the student's cohort year to the last cohort year in the file. Columns follow the financial aid
Analysis-Ready File dictionary, except that none of its identifying columns are generated: there
is no name, Social Security Number, date of birth or institution id here, and nothing downstream
expects one.

Two values come from the cohort file rather than from a draw, so the file agrees with the data
it sits beside: a student with Pell_Status_First_Year = Y gets a federal grant above zero, and
the unmet need band is tilted by the student's Retention outcome (see "The planted effect").

Dollar columns satisfy the dictionary's own arithmetic exactly:
    Unmet_Need = Cost_of_Attendance - EFC - Total_Institutional_Grants
                 - Total_State_Grants - Total_Federal_Grants
    Net_Price  = Cost_of_Attendance - Total_Institutional_Grants
                 - Total_State_Grants - Total_Federal_Grants
Both are floored at 0, as the dictionary requires.

The planted effect
-----------------
This file is invented, so a correlation found in it is a property of this generator and not a
finding about students. The relationship is deliberate and declared rather than accidental:
with --effect E, a student who was not retained is moved one band toward higher need with
probability E, and a retained student is moved one band toward lower need with the same
probability. --effect 0 produces a file independent of every outcome, which is the honest
setting for testing plumbing, and makes every downstream chart flat on purpose.

The effect and the seed are both written into every row's Source column, so a chart built on
this file can say which file it came from and how strong the planted relationship was.

Run from normalized-data-model/:
    python -m src.generator.enrichment.financial_aid
"""

import argparse
import csv
import random
import re
from pathlib import Path

__all__ = ["generate_financial_aid"]

# The bands, driest first. UNKNOWN is for a student with no ISIR, who has no EFC to compute from.
_BANDS = ("$0", "$1-2k", "$2-5k", "$5k+")
_UNKNOWN_BAND = "UNKNOWN"
# Each band's unmet need range in whole dollars, the upper bound excluded except for the last.
_BAND_RANGES = {"$0": (0, 1), "$1-2k": (1000, 2000), "$2-5k": (2000, 5000), "$5k+": (5000, 12000)}
_DEPENDENCY = ("D", "I", "X", "Y")
_HOUSING = ("1", "2", "3", "4")
# Cost of attendance for the first cohort year, rising by this much each later year.
_BASE_COST = 18000
_COST_RISE = 500
_SOURCE = (
    "synthetic: src/generator/enrichment/financial_aid.py, seed {seed}, planted effect {effect}"
)
_OUTPUT_COLUMNS = [
    "Student_GUID",
    "Academic_Year",
    "Dependency_Status",
    "Housing_Status",
    "Cost_of_Attendance",
    "EFC",
    "Total_Institutional_Grants",
    "Total_State_Grants",
    "Total_Federal_Grants",
    "Unmet_Need",
    "Net_Price",
    "Applied_Aid",
    "Unmet_Need_Band",
    "Source",
]


def generate_financial_aid(
    cohort_path="../data/raw/pdp_cohort_data.csv",
    output_path="data/input/enrichment/financial_aid.csv",
    applied=0.82,
    effect=0.35,
    seed=2026,
):
    """Write the financial aid enrichment file and return the rows written.

    applied: share of students with an ISIR record, so Applied_Aid = Y.
    effect: strength of the planted relationship with Retention. 0 means none.
    The same seed and effect always produce the same file.
    """
    students = _read_students(cohort_path)
    rows = _generate(students, applied, effect, seed)
    _write_rows(rows, output_path)
    return rows


def _next_academic_year(academic_year):
    """'2021-22' -> '2022-23'."""
    start = int(academic_year[:4]) + 1
    return f"{start}-{str(start + 1)[-2:]}"


def _year_range(first_year, last_year):
    """Every academic year from first_year to last_year, in order."""
    years = []
    year = first_year
    while year <= last_year:
        years.append(year)
        year = _next_academic_year(year)
    return years


def _read_students(cohort_path):
    """One (cohort, pell, retained) per student. A student with two cohort rows keeps the earlier one."""
    students = {}
    with open(cohort_path, newline="") as f:
        for line, row in enumerate(csv.DictReader(f), start=2):
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", row["Cohort"]):  # the year range needs a year to stop at
                raise ValueError(
                    f"{cohort_path} line {line}: Cohort {row['Cohort']!r} is not a YYYY-YY academic year"
                )
            guid = row["Student_GUID"]
            entry = (row["Cohort"], row["Pell_Status_First_Year"].strip().upper(), _retained(row))
            if guid not in students or entry[0] < students[guid][0]:
                students[guid] = entry
    return students


def _retained(row):
    """True, False or None for the student's Retention value, which the cohort file writes as 1 or 0."""
    value = row.get("Retention", "").strip()
    return {"1": True, "0": False}.get(value)


def _band_index(retained, effect, rng):
    """A band index, moved one step by the planted effect: higher need if not retained, lower if retained."""
    index = rng.randrange(len(_BANDS))
    if retained is None or rng.random() >= effect:
        return index
    return min(index + 1, len(_BANDS) - 1) if not retained else max(index - 1, 0)


def _dollars(band, cost, pell, rng):
    """Dollar columns for one row, built backwards from the band so the dictionary's arithmetic holds."""
    low, high = _BAND_RANGES[band]
    unmet = rng.randrange(low, high)
    federal = rng.randrange(1000, 7400) if pell == "Y" else 0
    institutional = rng.choice((0, 0, 500, 1000, 2000))
    state = rng.choice((0, 0, 0, 750, 1500))
    grants = federal + institutional + state
    # EFC is whatever the dictionary's formula leaves, floored at 0. Flooring can only lower unmet need.
    efc = max(0, cost - grants - unmet)
    unmet = max(0, cost - efc - grants)
    return {
        "Cost_of_Attendance": cost,
        "EFC": efc,
        "Total_Institutional_Grants": institutional,
        "Total_State_Grants": state,
        "Total_Federal_Grants": federal,
        "Unmet_Need": unmet,
        "Net_Price": max(0, cost - grants),
    }


def _band_for(unmet_need):
    """The band an unmet need amount falls in. The file's own band column is built with this."""
    for band in _BANDS:
        low, high = _BAND_RANGES[band]
        if low <= unmet_need < high:
            return band
    return _BANDS[-1]


def _generate(students, applied, effect, seed):
    """All aid rows, as dicts with _OUTPUT_COLUMNS. Same seed and effect, same rows."""
    rng = random.Random(seed)
    cohorts = [cohort for cohort, _, _ in students.values()]
    last_year = max(cohorts)
    source = _SOURCE.format(seed=seed, effect=effect)
    rows = []
    for guid in sorted(students):
        cohort, pell, retained = students[guid]
        filed = rng.random() < applied
        band = _BANDS[_band_index(retained, effect, rng)] if filed else _UNKNOWN_BAND
        for number, year in enumerate(_year_range(cohort, last_year)):
            cost = _BASE_COST + _COST_RISE * number
            row = {
                "Student_GUID": guid,
                "Academic_Year": year,
                "Dependency_Status": rng.choice(_DEPENDENCY) if filed else "UK",
                "Housing_Status": rng.choice(_HOUSING),
                "Applied_Aid": "Y" if filed else "N",
                "Source": source,
            }
            if filed:
                amounts = _dollars(band, cost, pell, rng)
                row.update(amounts)
                # The stored band is read back from the amounts, so the two can never disagree.
                row["Unmet_Need_Band"] = _band_for(amounts["Unmet_Need"])
            else:
                # No ISIR means no EFC, so there is nothing to compute a need from. Left blank, not zero.
                row.update({name: "" for name in _OUTPUT_COLUMNS[4:11]})
                row["Unmet_Need_Band"] = _UNKNOWN_BAND
            rows.append({name: row[name] for name in _OUTPUT_COLUMNS})
    return rows


def _write_rows(rows, output_path):
    """Write the rows to a CSV, creating the folder if it isn't there."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _main(argv=None):
    """Run the generator from the command line."""
    parser = argparse.ArgumentParser(description="Generate the synthetic financial aid enrichment file.")
    parser.add_argument("--cohort", default="../data/raw/pdp_cohort_data.csv", help="cohort Analysis-Ready File")
    parser.add_argument("--output", default="data/input/enrichment/financial_aid.csv")
    parser.add_argument("--applied", type=float, default=0.82, help="share of students with an ISIR record")
    parser.add_argument("--effect", type=float, default=0.35,
                        help="strength of the planted relationship with Retention. 0 means none")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    rows = generate_financial_aid(args.cohort, args.output, args.applied, args.effect, args.seed)
    students = len({row["Student_GUID"] for row in rows})
    print(f"{len(rows)} rows for {students} students written to {args.output}")


if __name__ == "__main__":
    _main()
