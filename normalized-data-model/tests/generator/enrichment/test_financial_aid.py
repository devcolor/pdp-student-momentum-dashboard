import csv
import random

import pytest

from src.generator.enrichment import financial_aid as a
from src.generator.enrichment.financial_aid import generate_financial_aid

# The identifying columns the financial aid Analysis-Ready File dictionary starts with. None of them
# is generated, and a later column must not quietly reintroduce one. Compared as whole names, since
# a word like "institutional" belongs in a grant column. Student_GUID is the repo's pseudonymous key,
# used by the cohort and course files too, so it is not on this list.
IDENTIFYING = {
    "firstname", "middlename", "lastname", "name", "ssn", "socialsecuritynumber",
    "dateofbirth", "dob", "studentid", "institutionid",
}


def plain(column):
    """A column name with no case or underscores, for comparing against IDENTIFYING."""
    return column.lower().replace("_", "")


def write_cohort(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Cohort", "Student_GUID", "Pell_Status_First_Year", "Retention"])
        writer.writeheader()
        writer.writerows(rows)


def cohort_of(tmp_path, n, retention="1", pell="Y"):
    """A cohort file of n students spread over the four cohort years."""
    path = tmp_path / "cohort.csv"
    years = ["2021-22", "2022-23", "2023-24", "2024-25"]
    write_cohort(path, [
        {"Cohort": years[i % 4], "Student_GUID": f"G{i:04d}", "Pell_Status_First_Year": pell, "Retention": retention}
        for i in range(n)
    ])
    return path


def fake_students(n, retained=True, pell="Y"):
    """The shape _read_students returns: guid -> (cohort, pell, retained)."""
    years = ["2021-22", "2022-23", "2023-24", "2024-25"]
    return {f"S{i:05d}": (years[i % 4], pell, retained) for i in range(n)}


def read_output(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def test_only_public_api_is_generate_financial_aid():
    public = [name for name in vars(a) if not name.startswith("_") and callable(getattr(a, name))
              and getattr(getattr(a, name), "__module__", None) == a.__name__]
    assert public == ["generate_financial_aid"]
    assert a.__all__ == ["generate_financial_aid"]


def test_no_identifying_column_is_generated():
    assert {plain(column) for column in a._OUTPUT_COLUMNS} & IDENTIFYING == set()


def test_next_academic_year():
    assert a._next_academic_year("2021-22") == "2022-23"
    assert a._next_academic_year("2099-00") == "2100-01"


def test_year_range_is_inclusive_and_in_order():
    assert a._year_range("2021-22", "2023-24") == ["2021-22", "2022-23", "2023-24"]
    assert a._year_range("2022-23", "2022-23") == ["2022-23"]


def test_read_students_keeps_the_earlier_cohort(tmp_path):
    path = tmp_path / "cohort.csv"
    write_cohort(path, [
        {"Cohort": "2022-23", "Student_GUID": "A", "Pell_Status_First_Year": "N", "Retention": "0"},
        {"Cohort": "2021-22", "Student_GUID": "A", "Pell_Status_First_Year": "Y", "Retention": "1"},
    ])
    assert a._read_students(path) == {"A": ("2021-22", "Y", True)}


def test_read_students_normalizes_pell_and_reads_retention(tmp_path):
    path = tmp_path / "cohort.csv"
    write_cohort(path, [
        {"Cohort": "2022-23", "Student_GUID": "A", "Pell_Status_First_Year": " y ", "Retention": "1"},
        {"Cohort": "2022-23", "Student_GUID": "B", "Pell_Status_First_Year": "N", "Retention": "0"},
        {"Cohort": "2022-23", "Student_GUID": "C", "Pell_Status_First_Year": "", "Retention": ""},
    ])
    assert a._read_students(path) == {
        "A": ("2022-23", "Y", True),
        "B": ("2022-23", "N", False),
        "C": ("2022-23", "", None),
    }


@pytest.mark.parametrize("cohort", ["UK", "", "2022"])
def test_read_students_rejects_a_cohort_that_is_not_an_academic_year(tmp_path, cohort):
    path = tmp_path / "cohort.csv"
    write_cohort(path, [
        {"Cohort": "2022-23", "Student_GUID": "A", "Pell_Status_First_Year": "Y", "Retention": "1"},
        {"Cohort": cohort, "Student_GUID": "B", "Pell_Status_First_Year": "Y", "Retention": "1"},
    ])
    with pytest.raises(ValueError, match=f"line 3: Cohort '{cohort}' is not a YYYY-YY academic year"):
        a._read_students(path)


def test_band_for_matches_the_band_ranges():
    assert a._band_for(0) == "$0"
    assert a._band_for(1500) == "$1-2k"
    assert a._band_for(2000) == "$2-5k"
    assert a._band_for(4999) == "$2-5k"
    assert a._band_for(5000) == "$5k+"
    assert a._band_for(999_999) == "$5k+"  # above every range, so the last band


def test_band_index_does_not_move_without_an_effect():
    rng = random.Random(1)
    assert all(0 <= a._band_index(False, 0.0, rng) < len(a._BANDS) for _ in range(50))


def test_band_index_moves_to_more_need_when_not_retained():
    # effect 1 always moves, so a non-retained student never lands in the driest band.
    rng = random.Random(2)
    assert all(a._band_index(False, 1.0, rng) > 0 for _ in range(200))


def test_band_index_moves_to_less_need_when_retained():
    rng = random.Random(3)
    assert all(a._band_index(True, 1.0, rng) < len(a._BANDS) - 1 for _ in range(200))


def test_band_index_ignores_an_unknown_retention():
    # A student with no Retention value can't be tilted either way, whatever the effect.
    rng = random.Random(4)
    assert all(0 <= a._band_index(None, 1.0, rng) < len(a._BANDS) for _ in range(50))


@pytest.mark.parametrize("band", a._BANDS)
def test_dollars_satisfy_the_dictionary_formula(band):
    rng = random.Random(5)
    for _ in range(100):
        row = a._dollars(band, a._BASE_COST, "Y", rng)
        grants = row["Total_Institutional_Grants"] + row["Total_State_Grants"] + row["Total_Federal_Grants"]
        assert row["Unmet_Need"] == max(0, row["Cost_of_Attendance"] - row["EFC"] - grants)
        assert row["Net_Price"] == max(0, row["Cost_of_Attendance"] - grants)
        assert row["EFC"] >= 0 and row["Unmet_Need"] >= 0


def test_dollars_give_a_federal_grant_only_to_a_pell_student():
    rng = random.Random(6)
    assert all(a._dollars("$1-2k", a._BASE_COST, "Y", rng)["Total_Federal_Grants"] > 0 for _ in range(50))
    assert all(a._dollars("$1-2k", a._BASE_COST, "N", rng)["Total_Federal_Grants"] == 0 for _ in range(50))


def test_generate_writes_one_row_per_student_per_remaining_year():
    rows = a._generate(fake_students(4), applied=1.0, effect=0.0, seed=7)
    by_student = {}
    for row in rows:
        by_student.setdefault(row["Student_GUID"], []).append(row["Academic_Year"])
    # The four fake students start in each of the four years, so they get 4, 3, 2 and 1 rows.
    assert sorted(len(years) for years in by_student.values()) == [1, 2, 3, 4]
    assert all(years == sorted(years) for years in by_student.values())


def test_generate_rows_fall_inside_the_cohort_file_years():
    rows = a._generate(fake_students(200), applied=0.8, effect=0.3, seed=8)
    assert {row["Academic_Year"] for row in rows} <= {"2021-22", "2022-23", "2023-24", "2024-25"}
    assert {row["Unmet_Need_Band"] for row in rows} <= set(a._BANDS) | {a._UNKNOWN_BAND}


def test_generate_applied_share_is_close_to_target():
    rows = a._generate(fake_students(4000), applied=0.82, effect=0.0, seed=9)
    filed = {row["Student_GUID"] for row in rows if row["Applied_Aid"] == "Y"}
    assert abs(len(filed) / 4000 - 0.82) < 0.02


def test_generate_leaves_every_amount_blank_when_no_aid_was_applied_for():
    rows = a._generate(fake_students(400), applied=0.0, effect=0.0, seed=10)
    assert rows and all(row["Applied_Aid"] == "N" for row in rows)
    for row in rows:
        # Blank, never zero: a non-filer has no EFC, so there is nothing to compute a need from.
        assert [row[name] for name in a._OUTPUT_COLUMNS[4:11]] == [""] * 7
        assert (row["Unmet_Need_Band"], row["Dependency_Status"]) == (a._UNKNOWN_BAND, "UK")


def test_generate_band_always_matches_the_amount():
    rows = a._generate(fake_students(500), applied=1.0, effect=0.4, seed=11)
    assert all(row["Unmet_Need_Band"] == a._band_for(row["Unmet_Need"]) for row in rows)


def test_generate_cost_of_attendance_rises_each_year():
    rows = a._generate(fake_students(4), applied=1.0, effect=0.0, seed=12)
    first = [row for row in rows if row["Student_GUID"] == "S00000"]  # the 2021-22 student, four years
    assert [row["Cost_of_Attendance"] for row in first] == [
        a._BASE_COST + a._COST_RISE * n for n in range(len(first))
    ]


def test_generate_is_independent_of_retention_without_an_effect():
    """effect 0 is the honest setting: the file says nothing about any outcome."""
    retained = a._generate(fake_students(3000, retained=True), applied=1.0, effect=0.0, seed=13)
    not_retained = a._generate(fake_students(3000, retained=False), applied=1.0, effect=0.0, seed=13)
    assert [row["Unmet_Need_Band"] for row in retained] == [row["Unmet_Need_Band"] for row in not_retained]


def test_generate_tilts_toward_more_need_when_the_effect_is_on():
    worst = a._BANDS[-1]
    retained = a._generate(fake_students(3000, retained=True), applied=1.0, effect=1.0, seed=14)
    not_retained = a._generate(fake_students(3000, retained=False), applied=1.0, effect=1.0, seed=14)
    share = [sum(row["Unmet_Need_Band"] == worst for row in rows) / len(rows) for rows in (retained, not_retained)]
    assert share[1] > share[0]


def test_generate_is_repeatable_for_a_seed_and_effect():
    students = fake_students(300)
    assert a._generate(students, 0.8, 0.3, seed=15) == a._generate(students, 0.8, 0.3, seed=15)
    assert a._generate(students, 0.8, 0.3, seed=15) != a._generate(students, 0.8, 0.3, seed=16)
    assert a._generate(students, 0.8, 0.3, seed=15) != a._generate(students, 0.8, 0.9, seed=15)


def test_source_names_the_generator_the_seed_and_the_effect():
    rows = a._generate(fake_students(20), applied=0.8, effect=0.25, seed=17)
    expected = "synthetic: src/generator/enrichment/financial_aid.py, seed 17, planted effect 0.25"
    assert all(row["Source"] == expected for row in rows)


def test_generate_financial_aid_writes_and_returns_rows(tmp_path):
    output = tmp_path / "out" / "financial_aid.csv"
    returned = generate_financial_aid(cohort_of(tmp_path, 100), output, seed=18)
    fieldnames, rows = read_output(output)
    assert fieldnames == a._OUTPUT_COLUMNS
    assert len(rows) == len(returned)
    assert {row["Student_GUID"] for row in rows} == {f"G{i:04d}" for i in range(100)}
    assert {row["Applied_Aid"] for row in rows} <= {"Y", "N"}


def test_command_line_end_to_end(tmp_path):
    output = tmp_path / "financial_aid.csv"
    a._main(["--cohort", str(cohort_of(tmp_path, 40)), "--output", str(output),
             "--seed", "19", "--applied", "1.0", "--effect", "0"])
    _, rows = read_output(output)
    assert rows and all(row["Applied_Aid"] == "Y" for row in rows)
    assert all(row["Unmet_Need_Band"] in a._BANDS for row in rows)
