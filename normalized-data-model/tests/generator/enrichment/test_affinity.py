import csv

from src.generator.enrichment import affinity as m
from src.generator.enrichment.affinity import generate_affinity


def write_cohort(path, guids):
    """Write a minimal cohort file with only the column the generator reads."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Student_GUID"])
        writer.writerows([g] for g in guids)


def test_only_public_api_is_generate_affinity():
    assert m.__all__ == ["generate_affinity"]


def test_shares_sum_to_one():
    assert abs(sum(m._AFFINITY_SHARES.values()) - 1.0) < 1e-9


def test_one_row_per_student_and_same_seed_same_file(tmp_path):
    cohort = tmp_path / "cohort.csv"
    write_cohort(cohort, [f"S{i}" for i in range(200)] + ["S0", ""])
    first = generate_affinity(cohort, tmp_path / "a.csv", seed=7)
    second = generate_affinity(cohort, tmp_path / "b.csv", seed=7)

    assert first == second
    assert len(first) == 200
    assert {r["Affinity"] for r in first} <= set(m._AFFINITY_SHARES)
    with open(tmp_path / "a.csv", newline="") as f:
        assert next(csv.reader(f)) == ["Student_GUID", "Affinity", "Source"]
