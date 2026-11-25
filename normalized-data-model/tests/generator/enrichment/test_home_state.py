import csv

from src.generator.enrichment import home_state as m
from src.generator.enrichment.home_state import generate_home_state


def write_cohort(path, guids):
    """Write a minimal cohort file with only the column the generator reads."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Student_GUID"])
        writer.writerows([g] for g in guids)


def test_only_public_api_is_generate_home_state():
    assert m.__all__ == ["generate_home_state"]


def test_shares_sum_to_one():
    assert abs(sum(m._STATE_SHARES.values()) - 1.0) < 1e-9


def test_one_row_per_student_and_same_seed_same_file(tmp_path):
    cohort = tmp_path / "cohort.csv"
    write_cohort(cohort, [f"S{i}" for i in range(200)] + ["S0", ""])
    first = generate_home_state(cohort, tmp_path / "a.csv", seed=7)
    second = generate_home_state(cohort, tmp_path / "b.csv", seed=7)

    assert first == second
    assert len(first) == 200
    assert {r["Home_State"] for r in first} <= set(m._STATE_SHARES)
    with open(tmp_path / "a.csv", newline="") as f:
        assert next(csv.reader(f)) == ["Student_GUID", "Home_State", "Source"]


def test_most_students_are_from_the_home_state(tmp_path):
    cohort = tmp_path / "cohort.csv"
    write_cohort(cohort, [f"S{i}" for i in range(2000)])
    rows = generate_home_state(cohort, tmp_path / "a.csv", seed=7)

    in_state = sum(r["Home_State"] == "IL" for r in rows) / len(rows)
    assert 0.8 < in_state < 0.92
