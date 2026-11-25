import csv

from src.generator.enrichment import all_students_extras as m
from src.generator.enrichment.all_students_extras import generate_all_students_extras


def write_inputs(folder, guids):
    """A minimal cohort file, home states (every student in Indiana) and affinity groups (Band)."""
    with open(folder / "cohort.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Student_GUID"])
        writer.writerows([g] for g in guids)
    with open(folder / "home.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Student_GUID", "Home_State", "Source"])
        writer.writerows([g, "IN", "test"] for g in guids)
    with open(folder / "affinity.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Student_GUID", "Affinity", "Source"])
        writer.writerows([g, "Band", "test"] for g in guids)


def test_only_public_api_is_generate_all_students_extras():
    assert m.__all__ == ["generate_all_students_extras"]


def test_weights_sum_to_one_and_there_are_five_diets():
    assert abs(sum(m._SIBLING_WEIGHTS) - 1.0) < 1e-9
    assert abs(sum(m._DIET_WEIGHTS) - 1.0) < 1e-9
    assert len(m._DIETS) == 5


def test_one_row_per_student_same_seed_same_file_and_zip_matches_home_state(tmp_path):
    write_inputs(tmp_path, [f"S{i}" for i in range(200)] + ["S0", ""])
    args = (tmp_path / "cohort.csv", tmp_path / "home.csv", tmp_path / "affinity.csv")
    first = generate_all_students_extras(*args, tmp_path / "a.csv", seed=7)
    second = generate_all_students_extras(*args, tmp_path / "b.csv", seed=7)

    assert first == second
    assert len(first) == 200
    assert all(460 <= int(row["Home_Zip"][:3]) <= 479 for row in first)
    assert {(row["State"], row["Affinity_Group"]) for row in first} == {("IN", "Band")}
    assert {row["Dietary_Restriction"] for row in first} <= set(m._DIETS)
    assert {int(row["Number_Of_Siblings"]) for row in first} <= set(m._SIBLINGS)


def test_the_file_is_the_long_shape_supplemental_uploads_use(tmp_path):
    write_inputs(tmp_path, ["S1"])
    generate_all_students_extras(
        tmp_path / "cohort.csv", tmp_path / "home.csv", tmp_path / "affinity.csv", tmp_path / "a.csv", seed=7
    )

    with open(tmp_path / "a.csv", newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["Student_GUID", "Academic_Year", "Academic_Term", "Attribute_Key", "Attribute_Value", "Source"]
    assert [row[3] for row in rows[1:]] == [
        "state", "home_zip", "affinity_group", "number_of_siblings", "dietary_restriction"
    ]
    assert rows[1][5].startswith("supplemental: all_students_extras.csv")
