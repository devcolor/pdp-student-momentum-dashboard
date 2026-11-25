"""Checks hiding on a full load of the mock data: every measure, cohort and breakdown the manifest publishes.

Run from the repo root: python -m pytest -m slow measures/tests/test_full_data.py
"""
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from measures import run_measures
from measures.manifest import MANIFEST, load_manifest
from measures.models import Status
from measures.run_measures import ACROSS_NOTE, COMPLEMENT_NOTE, hide_across_cohorts, lines_by_key, run_measure
from measures.tests.leaks import every_line, recoverable, weak_covers, worked_out

REPO = Path(__file__).resolve().parents[2]
MODEL = REPO / "normalized-data-model"


@pytest.fixture(scope="module")
def full_load(tmp_path_factory) -> Path:
    """The full mock data, loaded into a temporary SQLite file with the data model's own pipeline settings."""
    folder = tmp_path_factory.mktemp("load")
    settings = yaml.safe_load((MODEL / "config" / "pipeline.yaml").read_text(encoding="utf-8"))
    settings["backend"] = "sqlite"
    settings["sqlite"]["path"] = str(folder / "pdp.sqlite")
    settings["tables"]["path"] = str(folder / "tables")
    settings["logs_dir"] = str(folder / "logs")
    settings["staging_dir"] = str(folder / "staging")
    config = folder / "pipeline.yaml"
    config.write_text(yaml.safe_dump(settings), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "src.loader.load", "--config", str(config)], cwd=MODEL, check=True,
                   capture_output=True)
    return folder / "pdp.sqlite"


# One test, so the full load runs once per machine rather than once per test.
@pytest.mark.slow
def test_no_published_line_has_one_hidden_group_anyone_is_counted_in(full_load, monkeypatch):
    # Record what hiding returns, with the counts it saw, for every run publish.py makes.
    runs = []

    def recording(results, all_counts):
        """hide_across_cohorts (which runs after hide_complements), keeping its rows and counts."""
        rows = hide_across_cohorts(results, all_counts)
        runs.append((rows, all_counts))
        return rows

    monkeypatch.setattr(run_measures, "hide_across_cohorts", recording)
    manifest = load_manifest(MANIFEST)
    for measure, group_by in manifest.breakdowns.items():
        for cohorts in manifest.runs(measure):
            run_measure(measure, cohorts, list(group_by), database=full_load)

    covers = across = weak = 0
    found = {}
    for rows, all_counts in runs:
        measure = rows[0].measure.value
        by_key = {(r.cohort, r.group): r for r in rows}

        def counted(key):
            # A hidden group nobody is counted in adds 0 / 0 to the line: subtraction gives nothing away.
            return all_counts[key].denominator > 0

        # Each cohort's own lines, a deeper total in the run among them: any shown row could have been hidden.
        own, _ = lines_by_key(by_key)
        for key, groups in own.items():
            hidden = [g for g in groups if by_key[(key[0], g)].suppressed and counted((key[0], g))]
            shown = [g for g in groups if not by_key[(key[0], g)].suppressed]
            assert len(hidden) != 1 or not shown, (measure, key[0].label, hidden[0].label)
        for line in every_line(by_key):
            hidden = [key for key in line if by_key[key].suppressed and counted(key)]
            # A pooled row is never hidden as cover, so only a single cohort's shown row could have been.
            shown = [key for key in line if not by_key[key].suppressed and len(key[0].years) == 1]
            # A pool with no answers yet (completion's) publishes no numbers, so there's nothing to subtract from.
            no_answers_yet = len(hidden) == 1 and by_key[hidden[0]].status == Status.NOT_YET_OBSERVABLE
            assert len(hidden) != 1 or not shown or no_answers_yet, (measure, hidden[0][0].label, hidden[0][1].label)
        # What a reader of the published rows can work out by combining lines. The single years must add nothing:
        # a pooled group that comes out of the pool's rows alone is the README's multi-line limit, not theirs.
        published = [r for r in rows if manifest.approves(r.measure, r.cohort, r.group)]
        pooled = [r for r in published if len(r.cohort.years) > 1]
        if len(pooled) < len(published):
            assert worked_out(published, all_counts) == worked_out(pooled, all_counts), measure
        # Every relation among the published rows solved together, which catches what no single line gives,
        # such as a course minus its course x race and course x gender rows plus their course x gender x race.
        # The manifest runs each measure and cohort once, so a total outside the run is published nowhere.
        assert recoverable(published, all_counts, totals_published=False) == [], measure
        # Strict: totals outside the run taken as published too, as hiding takes them.
        given_back = recoverable(published, all_counts)
        if given_back:
            found[measure] = given_back
        weak += len(weak_covers(rows, all_counts))
        covers += sum(COMPLEMENT_NOTE in r.note or ACROSS_NOTE in r.note for r in rows)
        across += sum(ACROSS_NOTE in r.note for r in rows)
    print(f"\n{covers} cover rows, {across} of them hidden for a pooled cohort's line, {weak} weak")
    assert len(runs) == sum(len(manifest.runs(measure)) for measure in manifest.breakdowns)
    assert covers > 0
    assert across > 0
    assert weak == 0
    # The strict solve gives back one row: gender X is one student, so the pooled X x Two or More Races row is the
    # X total, and dfw_rate and credit_completion publish no one-way gender row that hiding could cover.
    one_student = [("2021-22 + 2022-23 + 2023-24", "gender=X, race=Two or More Races")]
    assert found == {"credit_completion": one_student, "dfw_rate": one_student}
