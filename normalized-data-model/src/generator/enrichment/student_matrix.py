"""Generate the synthetic student matrix enrichment file.

The only public API is generate_student_matrix(). It stands in for an institution's "student
matrix" export: one row per student per fall term they took courses in, with every column that
export has and the PDP Analysis-Ready Files don't, plus the keys (Student_GUID, Academic_Year,
Academic_Term). No value comes from that export. Its column layout and category labels were the
model; its rows were never read into this repo.

Derived from the mock cohort and course files, so they agree with the data they sit beside:
    New_Or_Returning          new in the student's cohort fall, else returning.
    Student_Level             the IPEDS level: first_time / new_transfer / other, full or part
                              time, degree-seeking or not.
    Degree_Seeking            false when Credential_Type_Sought_Year_1 is a non-credential program
                              or "Degree Seeking(N)". UNKNOWN counts as degree-seeking.
    Full_Time                 12 or more credits attempted that fall.
    College_Ready             not_college_ready when the math or English placement is N.
    Term_Rank                 how many terms with courses, up to and including this fall.
    Term_GPA, Cumulative_GPA  credit-weighted; only numeric grades and F (as 0) count.
    Academic_Standing         good_standing when Cumulative_GPA >= 2.0.
    Term_Credits_Attempted / _Completed / _Successful   successful means earned with a grade of
                              2.0 or better, or P.
    Retention_Fall_To_Spring  still_enrolled when the student has a SPRING course in the same
                              academic year. Blank for falls after the last spring in the file.
    IPEDS_Grad_Rate_Status, NCCBP_Grad_Rate_Status   only on a first-time full-time student's
                              cohort fall, from the cohort file's completion and last-enrollment
                              years. Completion counts within 150% time (3 years for an associate
                              or certificate, 6 for a bachelor's).

Drawn with a fixed seed:
    Educational_Goal, Promise_Status   once per student, independent of every outcome on purpose.
                              A chart that splits by either should come out flat.
    Age                       once per student within their PDP age band, plus a year per year
                              since their cohort. Age_Category is its band.
    Pell                      each fall, leaning toward the student's Pell_Status_First_Year.

Age and Pell are not independent: they lean on PDP columns, so they inherit the mock data's
existing gaps (cohort Retention is about 0.62 at Age_Category 18_19 and 0.46 at 25_29). Nothing
is planted on top of those gaps.

Run from normalized-data-model/:
    python -m src.generator.enrichment.student_matrix
"""

import argparse
import csv
import random
from collections import Counter
from pathlib import Path

__all__ = ["generate_student_matrix"]

_TERMS = ("FALL", "WINTER", "SPRING", "SUMMER")  # dictionary order within an academic year
_SOURCE = "synthetic: src/generator/enrichment/student_matrix.py, seed {seed} (its docstring says which columns are drawn)"
_KEY_COLUMNS = ["Student_GUID", "Academic_Year", "Academic_Term"]
_VALUE_COLUMNS = [
    "New_Or_Returning", "Student_Level", "Degree_Seeking", "Full_Time", "Pell", "Age", "Age_Category",
    "College_Ready", "Educational_Goal", "Promise_Status", "Term_Rank", "Term_GPA", "Cumulative_GPA",
    "Academic_Standing", "Term_Credits_Attempted", "Term_Credits_Completed", "Term_Credits_Successful",
    "Retention_Fall_To_Spring", "IPEDS_Grad_Rate_Status", "NCCBP_Grad_Rate_Status",
]
_OUTPUT_COLUMNS = _KEY_COLUMNS + _VALUE_COLUMNS + ["Source"]

_MIN_YEAR_SHARE = 0.01  # a year needs this share of student terms to count as in the data
_FULL_TIME_CREDITS = 12
_GOOD_STANDING_GPA = 2.0
_SUCCESS_POINTS = 2.0
_NON_DEGREE = ("Non Credential", "Degree Seeking(N)")  # Credential_Type_Sought_Year_1 prefixes

# Rounded shares, close to a typical community college's declared goals. Must sum to 1.
_GOAL_SHARES = {
    "graduate_and_transfer": 0.24,
    "graduate_and_find_job": 0.24,
    "take_classes_and_transfer": 0.20,
    "no_declaration": 0.16,
    "graduate_and_advance_in_job": 0.06,
    "take_classes_and_find_job": 0.04,
    "take_classes_to_advance_in_job": 0.04,
    "personal_enrichment": 0.02,
}
# Age at cohort entry, per PDP Student_Age band: [(first age, last age, weight)].
_AGE_RANGES = {
    "20 and younger": [(16, 17, 0.10), (18, 19, 0.70), (20, 20, 0.20)],
    ">20 - 24": [(21, 24, 1.0)],
    "Older than 24": [(25, 29, 0.40), (30, 34, 0.22), (35, 39, 0.14), (40, 49, 0.15), (50, 64, 0.09)],
}
_AGE_CATEGORIES = [(17, "under_18"), (19, "18_19"), (21, "20_21"), (24, "22_24"), (29, "25_29"),
                   (34, "30_34"), (39, "35_39"), (49, "40_49"), (64, "50_64")]
_PELL_CHANCE = {"Y": 0.85, "N": 0.10}  # chance of Pell in a fall, by first-year status; others get _PELL_OTHER
_PELL_OTHER = 0.33


def generate_student_matrix(
    cohort_path="../data/raw/pdp_cohort_data.csv",
    course_path="../data/raw/pdp_course_data.csv",
    output_path="data/input/enrichment/student_matrix.csv",
    promise_share=0.01,
    seed=2026,
):
    """Write the student matrix enrichment file and return the rows written.

    promise_share: share of students drawn as promise program participants.
    The same seed and input files always produce the same file.
    """
    students = _read_students(cohort_path)
    terms = _read_course_terms(course_path)
    rows = _generate(students, terms, promise_share, seed)
    _write_rows(rows, output_path)
    return rows


def _term_key(year, term):
    """Sort key for (academic_year, term): years in order, then terms in _TERMS order."""
    return year, _TERMS.index(term) if term in _TERMS else len(_TERMS)


def _number(text):
    """A cell as a float, or 0.0 when it's blank or the mock file's "." placeholder."""
    try:
        return float(text)
    except ValueError:
        return 0.0


def _whole(text):
    """A cell as an int, or 0 when it isn't a whole number."""
    return int(text) if text.isdigit() else 0


def _grade_points(grade):
    """A course grade as GPA points, or None when it doesn't count toward GPA (P, W, I, blank)."""
    if grade == "F":
        return 0.0
    try:
        points = float(grade)
    except ValueError:
        return None
    return points if 0.0 <= points <= 4.0 else None


def _read_students(cohort_path):
    """{student: cohort row}. A student with two cohort rows keeps the earlier cohort."""
    students = {}
    with open(cohort_path, newline="") as f:
        for row in csv.DictReader(f):
            guid = row["Student_GUID"]
            if guid not in students or row["Cohort"] < students[guid]["Cohort"]:
                students[guid] = row
    return students


def _read_course_terms(course_path):
    """{student: {(year, term): totals}} from the course file. Totals are summed credits and points."""
    terms = {}
    with open(course_path, newline="") as f:
        for row in csv.DictReader(f):
            year, term = row["Academic_Year"], row["Academic_Term"].upper()
            if not year or term not in _TERMS:
                continue
            totals = terms.setdefault(row["Student_GUID"], {}).setdefault(
                (year, term), {"attempted": 0.0, "earned": 0.0, "successful": 0.0, "points": 0.0, "graded": 0.0})
            attempted = _number(row["Number_of_Credits_Attempted"])
            earned = _number(row["Number_of_Credits_Earned"])
            points = _grade_points(row["Grade"])
            totals["attempted"] += attempted
            totals["earned"] += earned
            if row["Grade"] == "P" or (points is not None and points >= _SUCCESS_POINTS):
                totals["successful"] += earned
            if points is not None and attempted > 0:
                totals["points"] += points * attempted
                totals["graded"] += attempted
    return terms


def _draw_from(rng, shares):
    """One key of shares, weighted by its value."""
    keys = list(shares)
    return rng.choices(keys, weights=[shares[k] for k in keys])[0]


def _draw_age(rng, band):
    """An age at cohort entry inside the student's PDP age band, or None for an unknown band."""
    ranges = _AGE_RANGES.get(band)
    if ranges is None:
        return None
    first, last, _ = rng.choices(ranges, weights=[w for _, _, w in ranges])[0]
    return rng.randint(first, last)


def _age_category(age):
    """The student matrix's age band for an age."""
    for last, name in _AGE_CATEGORIES:
        if age <= last:
            return name
    return "65_plus"


def _gpa(points, credits):
    """A GPA to two decimals, or blank when there are no graded credits."""
    return f"{points / credits:.2f}" if credits > 0 else ""


def _flag(value):
    """True/False as the file's 'true'/'false'."""
    return "true" if value else "false"


def _credits(value):
    """Credits without a trailing .0 for whole numbers."""
    return f"{value:g}"


def _degree_seeking(cohort_row):
    """Whether the cohort row's credential sought is a degree or certificate."""
    return not cohort_row["Credential_Type_Sought_Year_1"].startswith(_NON_DEGREE)


def _grad_rate_statuses(cohort_row, last_data_year):
    """(IPEDS status, NCCBP status) for a first-time full-time student, from cohort file outcomes."""
    associate_years = _whole(cohort_row["Years_to_A_or_C_at_cohort_inst"])
    bachelor_years = _whole(cohort_row["Years_to_BA_at_cohort_inst"])
    completed = 1 <= associate_years <= 3 or 1 <= bachelor_years <= 6
    transferred = _whole(cohort_row["Years_of_Last_Enrollment_at_othe"]) > 0
    years_observed = int(last_data_year[:4]) - int(cohort_row["Cohort"][:4]) + 1
    still_enrolled = _whole(cohort_row["Years_of_Last_Enrollment_at_coho"]) >= years_observed
    if completed:
        return "completed", "degree_and_transferred" if transferred else "degree_not_transferred"
    if transferred:
        return "transferred", "no_degree_but_transferred"
    if still_enrolled:
        return "still_enrolled", "still_enrolled"
    return "dropped_out", "dropped_out"


def _student_level(is_first_fall, cohort_row, full_time, degree_seeking):
    """The IPEDS student level, in the student matrix's eight categories."""
    load = "full_time" if full_time else "part_time"
    if not degree_seeking:
        return f"{load}_non_degree_seeking"
    entry = "other"
    if is_first_fall and cohort_row["Enrollment_Type"] == "First-Time":
        entry = "first_time"
    elif is_first_fall and cohort_row["Enrollment_Type"] == "Transfer-In":
        entry = "new_transfer"
    return f"{entry}_{load}_degree_seeking"


def _student_rows(guid, cohort_row, student_terms, last_spring_year, last_data_year, rng, promise_share, source):
    """Every row for one student: one per fall they took courses in."""
    goal = _draw_from(rng, _GOAL_SHARES)
    promise = rng.random() < promise_share
    entry_age = _draw_age(rng, cohort_row["Student_Age"]) if cohort_row else None
    pell_chance = _PELL_CHANCE.get(cohort_row["Pell_Status_First_Year"], _PELL_OTHER) if cohort_row else _PELL_OTHER
    rows = []
    points = graded = 0.0
    for rank, (year, term) in enumerate(sorted(student_terms, key=lambda t: _term_key(*t)), start=1):
        totals = student_terms[(year, term)]
        points += totals["points"]
        graded += totals["graded"]
        if term != "FALL":
            continue
        pell = rng.random() < pell_chance  # drawn for every fall, so the stream doesn't depend on other columns
        full_time = totals["attempted"] >= _FULL_TIME_CREDITS
        cumulative = _gpa(points, graded)
        row = {
            "Student_GUID": guid, "Academic_Year": year, "Academic_Term": term,
            "Educational_Goal": goal,
            "Promise_Status": "promise" if promise else "non_promise",
            "Full_Time": _flag(full_time),
            "Pell": _flag(pell),
            "Term_Rank": str(rank),
            "Term_GPA": _gpa(totals["points"], totals["graded"]),
            "Cumulative_GPA": cumulative,
            "Academic_Standing": "" if not cumulative else (
                "good_standing" if float(cumulative) >= _GOOD_STANDING_GPA else "not_in_good_standing"),
            "Term_Credits_Attempted": _credits(totals["attempted"]),
            "Term_Credits_Completed": _credits(totals["earned"]),
            "Term_Credits_Successful": _credits(totals["successful"]),
            "Retention_Fall_To_Spring": "" if last_spring_year is None or year > last_spring_year else (
                "still_enrolled" if (year, "SPRING") in student_terms else "not_returning"),
            "Source": source,
        }
        if cohort_row:
            is_first_fall = year == cohort_row["Cohort"] and cohort_row["Cohort_Term"].upper() == "FALL"
            degree_seeking = _degree_seeking(cohort_row)
            not_ready = "N" in (cohort_row["Math_Placement"], cohort_row["English_Placement"])
            row.update({
                "New_Or_Returning": "new" if is_first_fall else "returning",
                "Student_Level": _student_level(is_first_fall, cohort_row, full_time, degree_seeking),
                "Degree_Seeking": _flag(degree_seeking),
                "College_Ready": "not_college_ready" if not_ready else "college_ready_or_undetermined",
            })
            if entry_age is not None:
                age = entry_age + int(year[:4]) - int(cohort_row["Cohort"][:4])
                row.update({"Age": str(age), "Age_Category": _age_category(age)})
            first_time_full_time = (cohort_row["Enrollment_Type"] == "First-Time"
                                    and cohort_row["Enrollment_Intensity_First_Term"] == "Full-Time")
            if is_first_fall and first_time_full_time:
                ipeds, nccbp = _grad_rate_statuses(cohort_row, last_data_year)
                row.update({"IPEDS_Grad_Rate_Status": ipeds, "NCCBP_Grad_Rate_Status": nccbp})
        rows.append({column: row.get(column, "") for column in _OUTPUT_COLUMNS})
    return rows


def _last_data_year(terms):
    """The latest academic year with at least _MIN_YEAR_SHARE of student terms.

    The mock course file has a few stray rows dated after its real end, which would make every
    recent student look like they'd left.
    """
    counts = Counter(year for student_terms in terms.values() for year, _ in student_terms)
    total = sum(counts.values())
    years = [year for year, count in counts.items() if count >= total * _MIN_YEAR_SHARE]
    return max(years) if years else None


def _generate(students, terms, promise_share, seed):
    """All rows, as dicts with _OUTPUT_COLUMNS. Same seed, same rows."""
    rng = random.Random(seed)
    all_terms = [t for student_terms in terms.values() for t in student_terms]
    springs = [year for year, term in all_terms if term == "SPRING"]
    last_spring_year = max(springs) if springs else None
    last_data_year = _last_data_year(terms)
    source = _SOURCE.format(seed=seed)
    rows = []
    for guid in sorted(terms):
        rows.extend(_student_rows(guid, students.get(guid), terms[guid], last_spring_year, last_data_year,
                                  rng, promise_share, source))
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
    parser = argparse.ArgumentParser(description="Generate the synthetic student matrix enrichment file.")
    parser.add_argument("--cohort", default="../data/raw/pdp_cohort_data.csv", help="cohort Analysis-Ready File")
    parser.add_argument("--course", default="../data/raw/pdp_course_data.csv", help="course Analysis-Ready File")
    parser.add_argument("--output", default="data/input/enrichment/student_matrix.csv")
    parser.add_argument("--promise_share", type=float, default=0.01, help="share of students in the promise program")
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    rows = generate_student_matrix(args.cohort, args.course, args.output, args.promise_share, args.seed)
    students = len({row["Student_GUID"] for row in rows})
    print(f"{len(rows)} rows for {students} students written to {args.output}")


if __name__ == "__main__":
    _main()
