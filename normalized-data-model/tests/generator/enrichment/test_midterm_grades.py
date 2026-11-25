import csv

from src.generator.enrichment import midterm_grades as m
from src.generator.enrichment.midterm_grades import generate_midterm_grades

COURSE_COLUMNS = m._KEY_COLUMNS + ["Course_Name", "Grade"]


def write_course(path, rows):
    """Write a minimal course file with only the columns the generator reads."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COURSE_COLUMNS)
        writer.writeheader()
        writer.writerows(dict(zip(COURSE_COLUMNS, row)) for row in rows)


def test_only_public_api_is_generate_midterm_grades():
    assert m.__all__ == ["generate_midterm_grades"]


def test_bands_follow_final_grade():
    assert [m._band(g) for g in ("4", "3.7", "A", "3", "2", "1", "0", "F", "W", "P", "", "M")] == [
        "high", "high", "high", "good", "middle", "low", "failed", "failed", "withdrew", "other", "other", "other",
    ]


def test_every_band_weights_sum_to_one():
    for weights in m._MIDTERM_WEIGHTS.values():
        assert len(weights) == len(m._MIDTERM_GRADES)
        assert abs(sum(weights) - 1.0) < 1e-9


def test_one_row_per_section_skips_blank_courses(tmp_path):
    course = tmp_path / "course.csv"
    write_course(course, [
        ("A", "2021-22", "FALL", "ENGL", "1301", "01", "COMP I", "4"),
        ("A", "2021-22", "FALL", "ENGL", "1301", "01", "COMP I", "4"),  # repeated key
        ("A", "2021-22", "FALL", "MATH", "1314", "02", "ALGEBRA", "W"),
        ("B", "2021-22", "", "", "", "", "", ""),                       # no course
    ])
    rows = generate_midterm_grades(course, tmp_path / "out.csv")

    assert [(r["Course_Prefix"], r["Course_Number"]) for r in rows] == [("ENGL", "1301"), ("MATH", "1314")]
    assert {r["Midterm_Grade"] for r in rows} <= set(m._MIDTERM_GRADES)


def test_same_seed_same_file_and_high_finals_never_fail_midterm(tmp_path):
    course = tmp_path / "course.csv"
    write_course(course, [(f"S{i}", "2021-22", "FALL", "ENGL", "1301", "01", "COMP I", "4") for i in range(100)])
    first = generate_midterm_grades(course, tmp_path / "a.csv", seed=7)
    second = generate_midterm_grades(course, tmp_path / "b.csv", seed=7)

    assert first == second
    assert {r["Midterm_Grade"] for r in first} <= {"A", "B", "C"}
