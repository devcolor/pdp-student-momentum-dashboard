import csv

from src.generator.enrichment import student_matrix as m
from src.generator.enrichment.student_matrix import generate_student_matrix

COURSE_COLUMNS = ["Student_GUID", "Academic_Year", "Academic_Term", "Grade",
                  "Number_of_Credits_Attempted", "Number_of_Credits_Earned"]
COHORT_DEFAULTS = {
    "Cohort": "2021-22", "Cohort_Term": "FALL", "Enrollment_Type": "First-Time",
    "Enrollment_Intensity_First_Term": "Full-Time", "Student_Age": "20 and younger",
    "Pell_Status_First_Year": "Y", "Credential_Type_Sought_Year_1": "Associate's Degree",
    "Math_Placement": "C", "English_Placement": "C",
    "Years_to_A_or_C_at_cohort_inst": "0", "Years_to_BA_at_cohort_inst": "0",
    "Years_of_Last_Enrollment_at_coho": "1", "Years_of_Last_Enrollment_at_othe": "0",
}


def write_csv(path, columns, rows):
    """Write rows (dicts) with the given header."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def write_cohort(path, students):
    """A cohort file: {guid: overrides of COHORT_DEFAULTS}."""
    rows = [{"Student_GUID": guid, **COHORT_DEFAULTS, **overrides} for guid, overrides in students.items()]
    write_csv(path, ["Student_GUID", *COHORT_DEFAULTS], rows)


def write_course(path, rows):
    """A course file from (guid, year, term, grade, attempted, earned) tuples."""
    write_csv(path, COURSE_COLUMNS, [dict(zip(COURSE_COLUMNS, row)) for row in rows])


def fall(rows, guid, year):
    """The one row for a student's fall."""
    found = [r for r in rows if r["Student_GUID"] == guid and r["Academic_Year"] == year]
    assert len(found) == 1
    return found[0]


def test_only_public_api_is_generate_student_matrix():
    assert m.__all__ == ["generate_student_matrix"]


def test_grade_points_counts_numbers_and_f_only():
    assert m._grade_points("3.7") == 3.7
    assert m._grade_points("F") == 0.0
    assert [m._grade_points(g) for g in ("P", "W", "", "I", "9")] == [None] * 5


def test_age_category_bands():
    assert [m._age_category(a) for a in (16, 18, 21, 24, 40, 65)] == [
        "under_18", "18_19", "20_21", "22_24", "40_49", "65_plus"]


def test_derived_columns_follow_the_cohort_and_course_files(tmp_path):
    write_cohort(tmp_path / "cohort.csv", {
        "A": {"Years_to_A_or_C_at_cohort_inst": "2", "Years_of_Last_Enrollment_at_othe": "3"},
        "B": {"Enrollment_Type": "Transfer-In", "Math_Placement": "N",
              "Credential_Type_Sought_Year_1": "Degree Seeking(N)"},
    })
    write_course(tmp_path / "course.csv", [
        ("A", "2021-22", "FALL", "4", "6", "6"),
        ("A", "2021-22", "FALL", "F", "6", "0"),
        ("A", "2021-22", "SPRING", "1", "3", "3"),
        ("A", "2022-23", "FALL", "P", "3", "3"),
        ("B", "2021-22", "FALL", "W", ".", "."),
        ("B", "2022-23", "SPRING", "4", "3", "3"),
    ])
    rows = generate_student_matrix(tmp_path / "cohort.csv", tmp_path / "course.csv", tmp_path / "out.csv")

    first = fall(rows, "A", "2021-22")
    assert first["New_Or_Returning"] == "new"
    assert first["Student_Level"] == "first_time_full_time_degree_seeking"
    assert first["Full_Time"] == "true"
    assert (first["Term_GPA"], first["Cumulative_GPA"], first["Academic_Standing"]) == ("2.00", "2.00", "good_standing")
    assert (first["Term_Credits_Attempted"], first["Term_Credits_Completed"], first["Term_Credits_Successful"]) == ("12", "6", "6")
    assert first["Retention_Fall_To_Spring"] == "still_enrolled"
    assert (first["IPEDS_Grad_Rate_Status"], first["NCCBP_Grad_Rate_Status"]) == ("completed", "degree_and_transferred")

    later = fall(rows, "A", "2022-23")
    assert later["New_Or_Returning"] == "returning"
    assert later["Term_Rank"] == "3"
    assert later["Term_GPA"] == ""  # a P counts for credits, not GPA
    assert later["Cumulative_GPA"] == "1.80"  # (4*6 + 0*6 + 1*3) / 15: the spring pulls it below 2.0
    assert later["Academic_Standing"] == "not_in_good_standing"
    assert later["IPEDS_Grad_Rate_Status"] == ""  # only on the cohort fall
    assert int(later["Age"]) == int(first["Age"]) + 1

    transfer = fall(rows, "B", "2021-22")
    assert transfer["Student_Level"] == "part_time_non_degree_seeking"
    assert transfer["College_Ready"] == "not_college_ready"
    assert transfer["Retention_Fall_To_Spring"] == "not_returning"
    assert transfer["Cumulative_GPA"] == "" and transfer["Academic_Standing"] == ""


def test_same_seed_same_file(tmp_path):
    write_cohort(tmp_path / "cohort.csv", {f"S{i}": {} for i in range(50)})
    write_course(tmp_path / "course.csv", [(f"S{i}", "2021-22", "FALL", "3", "3", "3") for i in range(50)])
    first = generate_student_matrix(tmp_path / "cohort.csv", tmp_path / "course.csv", tmp_path / "a.csv", seed=7)
    second = generate_student_matrix(tmp_path / "cohort.csv", tmp_path / "course.csv", tmp_path / "b.csv", seed=7)
    assert first == second
    assert {r["Educational_Goal"] for r in first} <= set(m._GOAL_SHARES)
