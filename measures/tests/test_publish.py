"""Checks manifest.yaml loading and the one-run publication on the tiny database (fixture.sql).

Run from the repo root: python -m pytest measures/tests
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from measures.manifest import MANIFEST, load_manifest
from measures.models import EVERYONE, Cohort, Group, GroupBy, GroupDimension, Measure
from measures.publish import MEASURE_TABLES, file_sha256, publication_path, publish

FIXTURE = Path(__file__).parent / "fixture.sql"
REPO = Path(__file__).resolve().parents[2]

SMALL_MANIFEST = """
version: 3
cohorts:
  - ["2022-23"]
measures:
  retention:
    - [pell]
    - [cohort_term]
    - [pell, cohort_term]
  dfw_rate:
    - [course]
"""


@pytest.fixture
def database():
    """The tiny database, in memory."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(FIXTURE.read_text(encoding="utf-8"))
    return connection


def write(tmp_path: Path, text: str) -> Path:
    """A manifest file holding text."""
    path = tmp_path / "manifest.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_committed_manifest_loads():
    manifest = load_manifest(MANIFEST)
    assert manifest.version >= 1
    assert Cohort.of("2021-22", "2022-23", "2023-24") in manifest.cohorts
    assert GroupBy.of(GroupDimension.RACE, GroupDimension.GENDER) in manifest.breakdowns[Measure.GATEWAY_MATH]


@pytest.mark.parametrize("measure", [Measure.DFW_RATE, Measure.CREDIT_COMPLETION])
def test_the_committed_manifest_approves_the_aid_breakdowns(measure):
    # Version 4: the aid momentum page reads these from the published file instead of running them live.
    manifest = load_manifest(MANIFEST)
    assert manifest.version >= 4
    assert GroupBy.of(GroupDimension.PELL) in manifest.breakdowns[measure]
    assert GroupBy.of(GroupDimension.UNMET_NEED_BAND) in manifest.breakdowns[measure]


def test_the_committed_manifest_approves_the_course_outcomes_all_choices():
    # Version 6: the course outcomes page's All races and All genders choices. Each measure is one run with
    # all its breakdowns, so a course x race row is hidden together with the course x gender x race rows in it.
    manifest = load_manifest(MANIFEST)
    assert manifest.version >= 6
    course, race, gender = GroupDimension.COURSE, GroupDimension.RACE, GroupDimension.GENDER
    for measure in (Measure.DFW_RATE, Measure.MIDTERM_ALERT_RATE):
        assert {GroupBy.of(course, race), GroupBy.of(course, gender), GroupBy.of(course, race, gender)} <= set(
            manifest.breakdowns[measure])
    for measure in (Measure.MIDTERM_ALERT_RATE, Measure.MIDTERM_RECOVERY_RATE):
        assert {GroupBy.of(race), GroupBy.of(gender), GroupBy.of(race, gender)} <= set(manifest.breakdowns[measure])
    for measure in (Measure.DFW_RATE, Measure.MIDTERM_ALERT_RATE, Measure.MIDTERM_RECOVERY_RATE):
        assert manifest.runs(measure) == [[cohort] for cohort in manifest.cohorts]


@pytest.mark.parametrize(
    "text, problem",
    [
        ("version: 0\ncohorts: [[2022-23]]\nmeasures: {retention: [[race]]}", "version"),
        ("version: 1\ncohorts: []\nmeasures: {retention: [[race]]}", "cohorts"),
        ("version: 1\ncohorts: [['2022-23']]\nmeasures: {graduation: [[race]]}", "not a measure"),
        ("version: 1\ncohorts: [['2022-23']]\nmeasures: {retention: [[race, gender, pell, age_band]]}", "1 to 3"),
        ("version: 1\ncohorts: [['2022-23']]\nmeasures: {retention: [[course]]}", "only dfw_rate"),
        ("version: 1\ncohorts: [['2022-23']]\nmeasures: {midterm_recovery_rate: [[course]]}", "midterm_alert_rate"),
        ("version: 1\ncohorts: [['2022-23']]\nmeasures: {retention: [[race], [race]]}", "twice"),
        ("version: 1\ncohorts: [['2022-23']]\nmeasures: {retention: [[shoe_size]]}", "shoe_size"),
        ("version: 1\ncohorts: [['2022-23', '2023-24'], ['2023-24', '2024-25']]\nmeasures: {retention: [[race]]}", "both hold 2023-24"),
        ("version: 1\ncohorts: [['2022-23', '2023-24'], ['2023-24']]\nmeasures: {retention: [[race]]}", "both hold 2023-24"),
    ],
)
def test_a_bad_manifest_says_what_is_wrong(tmp_path, text, problem):
    with pytest.raises(ValueError, match=problem):
        load_manifest(write(tmp_path, text))


POOLED = """
version: 5
cohorts:
  - ["2022-23", "2023-24"]
measures:
  retention:
    - [pell]
    - [cohort_term]
    - [pell, cohort_term]
  dfw_rate:
    - [course]
"""
SINGLES = """
single_cohorts:
  years: ["2022-23", "2023-24", "2024-25"]
  measures:
    retention:
      - [pell]
"""


def single_cohorts(years="['2022-23', '2023-24']", measures="{retention: [[race]]}"):
    """A manifest with one pool of 2022-23 and 2023-24, by race, and a single_cohorts block."""
    return (f"version: 5\ncohorts: [['2022-23', '2023-24']]\nmeasures: {{retention: [[race], [race, gender]], dfw_rate: [[course], [pell]]}}\n"
            f"single_cohorts: {{years: {years}, measures: {measures}}}")


@pytest.mark.parametrize(
    "text, problem",
    [
        (single_cohorts(years="['2022-23']"), "some of the years in 2022-23 \\+ 2023-24 but not 2023-24"),
        (single_cohorts(years="['2022-23', '2022-23']"), "a year twice"),
        (single_cohorts(years="2022-23"), "must be a list of years"),
        (single_cohorts(measures="{persistence: [[race]]}"), "lists persistence, which measures doesn't"),
        (single_cohorts(measures="{retention: [[pell]]}"), "by pell, which measures doesn't"),
        (single_cohorts(measures="{dfw_rate: [[pell]]}"), "course breakdown"),
        (single_cohorts(measures="{retention: [[shoe_size]]}"), "shoe_size"),
        ("version: 5\ncohorts: [['2022-23']]\nmeasures: {retention: [[race]]}\n"
         "single_cohorts: {years: ['2022-23'], measures: {retention: [[race]]}}", "already a cohort"),
        ("version: 5\ncohorts: [['2022-23']]\nmeasures: {retention: [[race]]}\nsingle_cohorts: {years: ['2023-24']}",
         "needs years and measures"),
    ],
)
def test_a_bad_single_cohorts_block_says_what_is_wrong(tmp_path, text, problem):
    with pytest.raises(ValueError, match=problem):
        load_manifest(write(tmp_path, text))


def test_single_cohorts_outside_every_pool_are_allowed(tmp_path):
    manifest = load_manifest(write(tmp_path, single_cohorts(years="['2022-23', '2023-24', '2024-25']")))
    assert manifest.single_cohorts == (Cohort.of("2022-23"), Cohort.of("2023-24"), Cohort.of("2024-25"))
    assert manifest.runs(Measure.RETENTION) == [[Cohort.of("2022-23", "2023-24"), *manifest.single_cohorts]]
    # A measure without single cohorts keeps one run per cohort.
    assert manifest.runs(Measure.DFW_RATE) == [[Cohort.of("2022-23", "2023-24")]]


def test_the_manifest_approves_only_the_single_cohorts_breakdowns(tmp_path):
    manifest = load_manifest(write(tmp_path, single_cohorts()))
    pool, single = Cohort.of("2022-23", "2023-24"), Cohort.of("2022-23")
    race = Group.of((GroupDimension.RACE, "Asian"))
    race_gender = Group.of((GroupDimension.RACE, "Asian"), (GroupDimension.GENDER, "F"))
    assert manifest.approves(Measure.RETENTION, pool, race_gender)
    assert manifest.approves(Measure.RETENTION, single, race)
    assert manifest.approves(Measure.RETENTION, single, EVERYONE)
    assert not manifest.approves(Measure.RETENTION, single, race_gender)
    assert not manifest.approves(Measure.DFW_RATE, single, EVERYONE)
    assert not manifest.approves(Measure.RETENTION, Cohort.of("2024-25"), EVERYONE)


def test_the_committed_manifest_publishes_single_cohorts_for_the_executive_view():
    manifest = load_manifest(MANIFEST)
    assert manifest.version >= 5
    one_way = {GroupBy.of(d) for d in (GroupDimension.RACE, GroupDimension.GENDER, GroupDimension.PELL,
                                       GroupDimension.AGE_BAND, GroupDimension.ENROLLMENT_INTENSITY)}
    assert {cohort.label for cohort in manifest.single_cohorts} == {"2021-22", "2022-23", "2023-24", "2024-25"}
    exec_view = (Measure.RETENTION, Measure.PERSISTENCE, Measure.GATEWAY_MATH, Measure.GATEWAY_ENGLISH,
                 Measure.FALL_TO_SPRING_RETENTION, Measure.COMPLETION)
    for measure in exec_view:
        assert set(manifest.single_breakdowns[measure]) == one_way
    make_up = {GroupBy.of(d) for d in (GroupDimension.RACE, GroupDimension.GENDER, GroupDimension.PELL)}
    for measure in (Measure.TRANSFER_IN_SHARE, Measure.PART_TIME_SHARE):
        assert set(manifest.single_breakdowns[measure]) == make_up
    assert set(manifest.single_breakdowns) == {*exec_view, Measure.TRANSFER_IN_SHARE, Measure.PART_TIME_SHARE}


def test_the_committed_manifest_has_no_trend_where_year_2_is_unfinished():
    # Version 7: retention and persistence need year 2, which 2024-25 hasn't fully had.
    manifest = load_manifest(MANIFEST)
    assert manifest.version >= 7
    assert manifest.no_trend == {Measure.RETENTION: frozenset({"2024-25"}), Measure.PERSISTENCE: frozenset({"2024-25"})}


def published_rows(results: Path, table: str, cohort: str) -> set:
    """Every row of one table for one cohort, leaving out when the data was loaded."""
    with sqlite3.connect(results) as connection:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})") if row[1] != "data_loaded_at"]
        return set(connection.execute(f"SELECT {', '.join(columns)} FROM {table} WHERE cohort = ?", (cohort,)))


def test_single_cohorts_leave_every_pooled_row_as_it_was(database, tmp_path):
    pooled, with_singles = tmp_path / "pooled.sqlite", tmp_path / "with_singles.sqlite"
    publish(database, pooled, write(tmp_path, POOLED))
    publish(database, with_singles, write(tmp_path, POOLED + SINGLES))

    for table in ("success_measures", "equity_gaps"):
        assert published_rows(with_singles, table, "2022-23 + 2023-24") == published_rows(pooled, table, "2022-23 + 2023-24")
    with sqlite3.connect(with_singles) as connection:
        singles = set(connection.execute(
            "SELECT measure, cohort, group_dimensions FROM success_measures WHERE cohort NOT LIKE '%+%'"))
        gap_singles = {row[0] for row in connection.execute(
            "SELECT DISTINCT group_dimensions FROM equity_gaps WHERE cohort NOT LIKE '%+%'")}
    # Only the breakdowns approved for the single years are kept, and only for retention.
    assert singles == {("retention", year, dimensions) for year in ("2022-23", "2023-24", "2024-25")
                       for dimensions in ("all", "pell")}
    assert gap_singles == {"pell"}


def test_publish_writes_every_approved_breakdown_and_a_record(database, tmp_path):
    results = tmp_path / "success_measures.sqlite"
    record = publish(database, results, write(tmp_path, SMALL_MANIFEST))

    with sqlite3.connect(results) as connection:
        saved = set(connection.execute("SELECT DISTINCT measure, group_dimensions FROM success_measures"))
        gap_measures = {row[0] for row in connection.execute("SELECT DISTINCT measure FROM equity_gaps")}
    assert saved == {
        ("retention", "all"), ("retention", "pell"), ("retention", "cohort_term"),
        ("retention", "cohort_term x pell"), ("dfw_rate", "all"), ("dfw_rate", "course"),
    }
    # The gap finder only compares yes-or-no measures, so DFW has no gap rows.
    assert gap_measures == {"retention"}
    assert record["manifest_version"] == 3
    assert record["results_sha256"] == file_sha256(results)
    assert json.loads(publication_path(results).read_text()) == record


def test_gaps_hide_every_group_the_measures_hide(database, tmp_path):
    # One run: a group the measures hide (for size or as cover) is hidden in the gaps too.
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, SMALL_MANIFEST))
    with sqlite3.connect(results) as connection:
        mismatched = connection.execute(
            """SELECT m.group_dimensions, m.group_values FROM success_measures m
               JOIN equity_gaps g USING (measure, cohort, group_dimensions, group_values)
               WHERE m.suppressed = 1 AND g.suppressed = 0"""
        ).fetchall()
    assert mismatched == []


def test_publish_replaces_the_whole_file(database, tmp_path):
    results = tmp_path / "success_measures.sqlite"
    with sqlite3.connect(results) as connection:
        connection.execute("CREATE TABLE leftover (x)")
    publish(database, results, write(tmp_path, SMALL_MANIFEST))
    with sqlite3.connect(results) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"success_measures", "equity_gaps", "measure_trends"}
    assert not results.with_name("success_measures.building.sqlite").exists()


def test_the_query_builder_accepts_what_publish_writes(database, tmp_path):
    # The builder keeps its own copy of the record's name and checksum, so this proves the two agree.
    sys.path.insert(0, str(REPO / "mcp"))
    try:
        from pdp_mcp.results import ResultsReader, Spec
    finally:
        sys.path.remove(str(REPO / "mcp"))
    manifest = write(tmp_path, SMALL_MANIFEST)
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, manifest)

    answer = ResultsReader(manifest, results).query(Spec(measure="retention", cohort="2022-23", group_by=["pell"]))
    assert answer.everyone.group == {}
    assert answer.everyone.denominator > 0
    assert answer.rows and all(set(row.group) == {"pell"} for row in answer.rows)
    assert answer.manifest_version == 3


def test_course_measures_can_be_broken_down_by_course(tmp_path):
    text = "version: 1\ncohorts: [['2022-23']]\nmeasures: {midterm_alert_rate: [[course], [course, race, gender]]}"
    manifest = load_manifest(write(tmp_path, text))
    assert GroupBy.of(GroupDimension.COURSE) in manifest.breakdowns[Measure.MIDTERM_ALERT_RATE]


def test_affinity_and_educational_goal_publish_rates_but_no_gaps(database, tmp_path):
    text = """
version: 1
cohorts:
  - ["2022-23"]
measures:
  retention:
    - [pell]
    - [affinity]
    - [educational_goal]
"""
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, text))
    with sqlite3.connect(results) as connection:
        rates = {row[0] for row in connection.execute("SELECT DISTINCT group_dimensions FROM success_measures")}
        gaps = {row[0] for row in connection.execute("SELECT DISTINCT group_dimensions FROM equity_gaps")}
    assert rates == {"all", "pell", "affinity", "educational_goal"}
    assert "affinity" not in gaps and "educational_goal" not in gaps
    assert "pell" in gaps



def test_a_model_loaded_before_a_table_says_to_load_it_again(database, tmp_path):
    """The old failure was `no such table` part way through, after minutes of work."""
    database.execute("DROP TABLE student_term_matrix")

    with pytest.raises(ValueError, match="student_term_matrix") as refused:
        publish(database, tmp_path / "out.sqlite", write(tmp_path, SMALL_MANIFEST))

    message = str(refused.value)
    assert "loaded before that table existed" in message
    assert "python -m src.pipeline.run" in message


def test_every_table_the_measures_read_is_listed(database):
    """MEASURE_TABLES is written out, so this keeps it honest against the fixture's schema."""
    loaded = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert MEASURE_TABLES <= loaded


def test_a_failed_publish_keeps_the_last_good_results(database, tmp_path):
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, SMALL_MANIFEST))
    before, record_before = results.read_bytes(), publication_path(results).read_bytes()

    with pytest.raises(ValueError, match="1999-00"):
        publish(database, results, write(tmp_path, SMALL_MANIFEST.replace("2022-23", "1999-00")))

    assert results.read_bytes() == before
    assert publication_path(results).read_bytes() == record_before
    assert not results.with_name("success_measures.building.sqlite").exists()


def test_a_publish_failing_part_way_leaves_nothing_half_built(database, tmp_path, monkeypatch):
    # The first measure is saved to the building file before the second one fails.
    import measures.publish as publish_module

    calls = []
    real_run = publish_module.run_measure

    def fail_second(*args, **kwargs):
        """run_measure, failing on its second call."""
        calls.append(args)
        if len(calls) == 2:
            raise RuntimeError("stopped part way")
        return real_run(*args, **kwargs)

    monkeypatch.setattr(publish_module, "run_measure", fail_second)
    results = tmp_path / "success_measures.sqlite"
    with pytest.raises(RuntimeError, match="part way"):
        publish(database, results, write(tmp_path, SMALL_MANIFEST))

    assert not results.exists()
    assert list(tmp_path.glob("*.building*")) == []


def test_the_record_matches_the_swapped_in_file(database, tmp_path):
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, SMALL_MANIFEST))
    record = publish(database, results, write(tmp_path, POOLED))

    assert json.loads(publication_path(results).read_text()) == record
    assert record["results_sha256"] == file_sha256(results)
    assert record["manifest_version"] == 5
    assert record["data_loaded_at"] == "2026-01-01T00:00:00"  # SQLite's text, unchanged
    assert list(tmp_path.glob("*.building*")) == []


def test_latest_load_gives_the_same_string_for_text_and_a_timestamp():
    # PostgreSQL's TIMESTAMP comes back as a datetime; SQLite's is the loader's ISO text.
    from datetime import datetime

    from measures.run_measures import latest_load

    text = [("a.csv", "x", "2026-01-01T00:00:00"), ("b.csv", "y", "2025-12-31T23:00:00")]
    stamped = [("a.csv", "x", datetime(2026, 1, 1)), ("b.csv", "y", datetime(2025, 12, 31, 23))]
    assert latest_load(text) == latest_load(stamped) == "2026-01-01T00:00:00"
    assert latest_load([]) == "unknown"


def with_no_trend(no_trend: str) -> str:
    """single_cohorts() with a no_trend entry added to its block."""
    return single_cohorts(years="['2022-23', '2023-24', '2024-25']").removesuffix("}") + f", no_trend: {no_trend}}}"


def test_no_trend_is_read_per_measure(tmp_path):
    manifest = load_manifest(write(tmp_path, with_no_trend("{retention: ['2024-25']}")))
    assert manifest.no_trend == {Measure.RETENTION: frozenset({"2024-25"})}
    assert load_manifest(write(tmp_path, single_cohorts())).no_trend == {}


@pytest.mark.parametrize(
    "no_trend, problem",
    [
        ("{persistence: ['2024-25']}", "persistence, which has no single cohorts"),
        ("{retention: ['2030-31']}", "2030-31, which isn't a single cohort"),
        ("{retention: []}", "must be a list of years"),
        ("{shoe_size: ['2024-25']}", "shoe_size"),
        ("['2024-25']", "must map measures to years"),
    ],
)
def test_a_bad_no_trend_says_what_is_wrong(tmp_path, no_trend, problem):
    with pytest.raises(ValueError, match=problem):
        load_manifest(write(tmp_path, with_no_trend(no_trend)))


TRENDS = """
version: 7
cohorts:
  - ["2022-23", "2023-24"]
measures:
  retention:
    - [pell]
  completion:
    - [pell]
  transfer_in_share:
    - [pell]
single_cohorts:
  years: ["2022-23", "2023-24", "2024-25"]
  measures:
    retention:
      - [pell]
    completion:
      - [pell]
    transfer_in_share:
      - [pell]
"""


def published_trends(results: Path) -> dict:
    """Every measure_trends row, keyed (kpi, cohort, group_dimensions, group_values)."""
    with sqlite3.connect(results) as connection:
        rows = connection.execute(
            "SELECT kpi, cohort, group_dimensions, group_values, previous_cohort, relative_pct, direction, judgement, label"
            " FROM measure_trends")
        return {row[:4]: row[4:] for row in rows}


def shown(results: Path, measure: str, cohort: str) -> dict:
    """(group_values) -> (numerator, denominator, metric_rate) for one measure and cohort's shown rows."""
    with sqlite3.connect(results) as connection:
        rows = connection.execute(
            "SELECT group_values, numerator, denominator, metric_rate FROM success_measures"
            " WHERE measure = ? AND cohort = ? AND status = 'ok'", (measure, cohort))
        return {row[0]: row[1:] for row in rows}


def test_trends_are_written_only_between_two_shown_single_years(database, tmp_path):
    from measures.compare import compare_values

    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, TRENDS))
    trends = published_trends(results)

    # Retention: 2024-25 has no answers yet, so only 2023-24's change from 2022-23 is written.
    retention = {key: value for key, value in trends.items() if key[0] == "retention"}
    assert {key[1] for key in retention} == {"2023-24"}
    earlier, latest = shown(results, "retention", "2022-23"), shown(results, "retention", "2023-24")
    for (_, _, _, values), (previous, pct, direction, judgement, label) in retention.items():
        assert values in earlier and values in latest
        change = compare_values("retention", earlier[values][2], latest[values][2])
        assert (previous, pct, direction, judgement) == ("2022-23", change.relative_pct, change.direction, change.judgement)
        assert label == change.label("2022-23")
    # Every group shown in both years has its row, and no other.
    assert {key[3] for key in retention} == set(earlier) & set(latest)
    # Completion: 2023-24 and 2024-25 are short of the window, so nothing is compared.
    assert not any(key[0] == "completion" for key in trends)
    # No trend for a pool.
    assert not any("+" in key[1] for key in trends)


def test_entering_students_trend_comes_from_the_make_up_denominators(database, tmp_path):
    from measures.compare import compare_values

    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, TRENDS))
    trends = published_trends(results)
    entering = {key[1]: value for key, value in trends.items() if key[0] == "entering_students"}
    assert all(key[2:] == ("all", "all") for key in trends if key[0] == "entering_students")
    for latest, (previous, pct, *_rest, label) in entering.items():
        before = shown(results, "transfer_in_share", previous)["all"][1]
        now = shown(results, "transfer_in_share", latest)["all"][1]
        change = compare_values("entering_students", float(before), float(now))
        assert (pct, label) == (change.relative_pct, change.label(previous))
    assert set(entering) == {"2023-24", "2024-25"}


def test_no_trend_years_get_no_trend_rows(database, tmp_path):
    text = TRENDS.replace("version: 7", "version: 7").rstrip() + "\n  no_trend:\n    transfer_in_share: ['2024-25']\n"
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, text))
    cohorts = {key[1] for key in published_trends(results) if key[0] == "transfer_in_share"}
    assert cohorts == {"2023-24"}
    # The entering students' trend is not the measure's, so no_trend leaves it.
    assert {key[1] for key in published_trends(results) if key[0] == "entering_students"} == {"2023-24", "2024-25"}


def test_make_up_measures_publish_rates_but_no_gaps(database, tmp_path):
    results = tmp_path / "success_measures.sqlite"
    publish(database, results, write(tmp_path, TRENDS))
    with sqlite3.connect(results) as connection:
        gap_measures = {row[0] for row in connection.execute("SELECT DISTINCT measure FROM equity_gaps")}
    assert "transfer_in_share" not in gap_measures and "retention" in gap_measures
    assert shown(results, "transfer_in_share", "2022-23")["all"][1] > 0


def test_a_pool_with_no_answers_yet_hides_nothing_in_its_years(database, tmp_path):
    # Completion's 2023-24 is short of the window, so the pool publishes no numbers, and its single years
    # are hidden only as their own lines need: the same rows as 2022-23 published alone.
    results, alone = tmp_path / "with_pool.sqlite", tmp_path / "alone.sqlite"
    publish(database, results, write(tmp_path, TRENDS))
    publish(database, alone, write(tmp_path, "version: 1\ncohorts: [['2022-23']]\nmeasures: {completion: [[pell]]}\n"))
    assert published_rows(results, "success_measures", "2022-23") >= {
        row for row in published_rows(alone, "success_measures", "2022-23") if row[0] == "completion"}
    with sqlite3.connect(results) as connection:
        statuses = set(connection.execute(
            "SELECT status FROM success_measures WHERE measure = 'completion' AND cohort LIKE '%+%'"))
    assert statuses == {("not_yet_observable",)}
