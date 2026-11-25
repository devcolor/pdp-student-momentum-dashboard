"""playground/deploy/trim_measures.py: the deploy's smaller measures copy and its record."""

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from tests.published_results import COHORT, MANIFEST, ROWS, builder, publish, row

TRIM_SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "trim_measures.py"
COURSE_ROWS = [
    row("course", "MATH 101", 0.22, 400, measure="dfw_rate"),
    row("course", "ART 210", None, None, measure="dfw_rate"),
    row("course x gender x race", "MATH 101 x F x Asian", None, None, measure="dfw_rate"),
]


def load_trim():
    """The trim script as a module; playground/deploy isn't a package."""
    spec = importlib.util.spec_from_file_location("trim_measures", TRIM_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trim_measures = load_trim()


@pytest.fixture
def manifest(tmp_path: Path) -> Path:
    """The test manifest the full file is published from."""
    path = tmp_path / "manifest.yaml"
    path.write_text(MANIFEST, encoding="utf-8")
    return path


@pytest.fixture
def full(tmp_path: Path, manifest: Path) -> Path:
    """A published full measures file, with shown and hidden course rows."""
    folder = tmp_path / "full"
    folder.mkdir()
    return publish(folder / "success_measures.sqlite", manifest, ROWS + COURSE_ROWS)


def rows_in(path: Path) -> list[tuple]:
    """Every success_measures row's dimensions, values and status, sorted."""
    with sqlite3.connect(path) as connection:
        found = connection.execute(
            "SELECT group_dimensions, group_values, status FROM success_measures"
        ).fetchall()
    connection.close()
    return sorted(found)


def test_refuses_a_full_file_with_no_publication_record(
    tmp_path: Path, full: Path, manifest: Path
) -> None:
    full.with_name("success_measures.publication.json").unlink()
    target = tmp_path / "trimmed.sqlite"

    with pytest.raises(SystemExit, match="publish the results"):
        trim_measures.trim(full, target, manifest)
    assert not target.exists()


def test_refuses_a_full_file_changed_after_publishing(
    tmp_path: Path, full: Path, manifest: Path
) -> None:
    with sqlite3.connect(full) as connection:
        connection.execute(
            "UPDATE success_measures SET metric_rate = 0.5 WHERE group_values = 'Asian'"
        )
    connection.close()
    target = tmp_path / "trimmed.sqlite"

    with pytest.raises(SystemExit, match="changed after it was published"):
        trim_measures.trim(full, target, manifest)
    assert not target.exists()


def test_refuses_a_full_file_published_from_another_manifest(
    tmp_path: Path, full: Path, manifest: Path
) -> None:
    # The deploy reads the committed manifest; a file published from an older one must not go live.
    manifest.write_text(MANIFEST + "    - [gender]\n", encoding="utf-8")
    target = tmp_path / "trimmed.sqlite"

    with pytest.raises(SystemExit, match="different manifest"):
        trim_measures.trim(full, target, manifest)
    assert not target.exists()


def test_the_copy_drops_hidden_course_rows_only(tmp_path: Path, full: Path, manifest: Path) -> None:
    target = tmp_path / "trimmed.sqlite"
    trim_measures.trim(full, target, manifest)

    kept = rows_in(target)
    assert ("course", "MATH 101", "ok") in kept
    assert not [r for r in kept if r[0].startswith("course") and r[2] == "suppressed"]
    # Hidden rows outside the course splits stay, and so does every shown row.
    expected = [
        r for r in rows_in(full) if not (r[0].startswith("course") and r[2] == "suppressed")
    ]
    assert kept == expected


def test_the_copy_has_its_own_publication_record(
    tmp_path: Path, full: Path, manifest: Path
) -> None:
    target = tmp_path / "trimmed.sqlite"
    trim_measures.trim(full, target, manifest)

    source = json.loads(full.with_name("success_measures.publication.json").read_text())
    record = json.loads((tmp_path / "trimmed.publication.json").read_text())
    assert record["results_sha256"] == builder.file_sha256(target)
    assert record["trimmed_from_sha256"] == source["results_sha256"] == builder.file_sha256(full)
    assert record["manifest_sha256"] == source["manifest_sha256"]
    assert record["data_loaded_at"] == source["data_loaded_at"]
    assert "trimmed" in record


def test_the_query_builder_accepts_the_copy(tmp_path: Path, full: Path, manifest: Path) -> None:
    target = tmp_path / "trimmed.sqlite"
    trim_measures.trim(full, target, manifest)

    answer = builder.ResultsReader(manifest, target).query(
        builder.Spec(measure="gateway_math", cohort=COHORT, group_by=["race"])
    )
    assert [r.group["race"] for r in answer.rows] == [
        "Asian",
        "Native Hawaiian or Other Pacific Islander",
    ]
    assert answer.everyone.denominator == 3282
