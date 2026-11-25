"""The structured query builder (pdp_mcp/results.py) against a small published results file.

The file is written by conftest's `published` fixture, in the published layout, so these tests need
neither measures/ nor a loaded database. The data is made up.
"""

import json
import sqlite3

import pytest
from pydantic import ValidationError

from conftest import COHORT, MANIFEST, NOTE, measure_row
from pdp_mcp.results import MAX_ROWS, MAX_VALUE_LENGTH, ResultsReader, Spec, SpecRefused, file_sha256, like_pattern, publication_path, spec_sql


def ask(published, **spec):
    """The builder's answer to one spec."""
    manifest, results = published
    return ResultsReader(manifest, results).query(Spec(**spec))


def add_rows(published, measures=(), gaps=()):
    """Add success_measures rows and (measure, dimensions, values, status, students_affected) gap rows,
    then publish the file again so the builder trusts it."""
    _, results = published
    with sqlite3.connect(results) as connection:
        connection.executemany("INSERT INTO success_measures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", measures)
        for measure, dimensions, values, status, affected in gaps:
            shown = None if status != "ok" else affected
            connection.execute("INSERT INTO equity_gaps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               (measure, COHORT, dimensions, values, status, shown and -5.0, shown and -9.0,
                                shown and -1.0, shown and 0.01, None if shown is None else 0, shown, shown and 9))
    record_path = publication_path(results)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["results_sha256"] = file_sha256(results)
    record_path.write_text(json.dumps(record), encoding="utf-8")


def test_an_approved_spec_returns_its_breakdown_and_everyone(published):
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"])
    assert [row.group["race"] for row in answer.rows] == [
        "Asian", "Black or African American", "Native Hawaiian or Other Pacific Islander"]
    assert answer.everyone.group == {} and answer.everyone.denominator == 3282
    assert answer.manifest_version == 2 and answer.source == "synthetic"
    # A hidden group stays blank, never 0, and its note passes through.
    hidden = answer.rows[2]
    assert (hidden.status, hidden.numerator, hidden.metric_rate, hidden.note) == ("suppressed", None, None, NOTE)


def test_no_exclusion_counts_leave_the_builder(published):
    row = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"]).rows[0]
    assert not {"n_excluded", "n_out_of_scope", "exclusions"} & set(row.model_dump())


def test_group_by_order_doesnt_matter_and_where_slices(published):
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race", "gender"], where={"gender": "M"})
    assert [row.group for row in answer.rows] == [{"gender": "M", "race": "Black or African American"}]
    assert answer.rows[0].metric_rate == 0.1474


def test_gaps_come_from_the_published_gap_rows(published):
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"], include=["rates", "gaps"])
    men = next(row for row in answer.rows if row.group["gender"] == "M")
    assert (men.gap_pts, men.likely_noise, men.rank_by_affected) == (-13.92, False, 1)
    women = next(row for row in answer.rows if row.group["gender"] == "F")
    assert women.gap_pts is None   # the gap finder saved no row for it


@pytest.mark.parametrize(
    "spec, approved_key",
    [
        ({"measure": "graduation", "cohort": COHORT, "group_by": ["race"]}, "measures"),
        ({"measure": "gateway_math", "cohort": "2022-23", "group_by": ["race"]}, "cohorts"),
        ({"measure": "gateway_math", "cohort": COHORT, "group_by": ["pell"]}, "group_by"),
        ({"measure": "gateway_math", "cohort": COHORT, "group_by": ["race"], "where": {"gender": "M"}}, "group_by"),
    ],
)
def test_an_unapproved_spec_is_refused_with_what_is_approved(published, spec, approved_key):
    with pytest.raises(SpecRefused) as refused:
        ask(published, **spec)
    assert approved_key in refused.value.approved


SINGLES = """
single_cohorts:
  years: ["2021-22", "2022-23", "2023-24"]
  measures:
    gateway_math:
      - [race]
"""


def with_single_cohorts(published):
    """Add single_cohorts to the manifest and 2022-23 gateway_math rows to the file, then publish both again."""
    manifest, results = published
    manifest.write_text(MANIFEST + SINGLES, encoding="utf-8")
    rows = [measure_row("gateway_math", "all", "all", 0.3, 1100), measure_row("gateway_math", "race", "Asian", 0.33, 40)]
    with sqlite3.connect(results) as connection:
        connection.executemany("INSERT INTO success_measures VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               [(row[0], "2022-23", *row[2:]) for row in rows])
    record_path = publication_path(results)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["manifest_sha256"] = file_sha256(manifest)
    record["results_sha256"] = file_sha256(results)
    record_path.write_text(json.dumps(record), encoding="utf-8")
    return published


def test_single_cohorts_are_approved_after_the_pool_for_their_measures_only(published):
    approved = ResultsReader(*with_single_cohorts(published)).approved()
    assert approved["gateway_math"]["cohorts"] == [COHORT, "2021-22", "2022-23", "2023-24"]
    # The pool's breakdowns, as before: a single cohort's narrower list comes with a refusal.
    assert approved["gateway_math"]["group_by"] == [["race"], ["gender", "race"]]
    assert approved["dfw_rate"]["cohorts"] == [COHORT]


def test_breakdowns_name_what_each_cohort_may_be_split_by(published):
    reader = ResultsReader(*with_single_cohorts(published))
    assert reader.breakdowns("gateway_math", COHORT) == [["race"], ["gender", "race"]]
    # A single cohort has only its own narrower list.
    assert reader.breakdowns("gateway_math", "2022-23") == [["race"]]
    assert reader.breakdowns("dfw_rate", "2022-23") == []
    assert reader.breakdowns("gateway_math", "1999-00") == []
    assert reader.breakdowns("not_a_measure", COHORT) == []


def test_a_single_cohort_answers_its_approved_breakdown(published):
    answer = ask(with_single_cohorts(published), measure="gateway_math", cohort="2022-23", group_by=["race"])
    assert [(row.group["race"], row.denominator) for row in answer.rows] == [("Asian", 40)]
    assert answer.everyone.denominator == 1100


def test_a_single_cohort_refuses_a_breakdown_only_the_pool_has(published):
    with pytest.raises(SpecRefused, match="isn't approved for 2022-23") as refused:
        ask(with_single_cohorts(published), measure="gateway_math", cohort="2022-23", group_by=["race", "gender"])
    assert refused.value.approved == {"group_by": [["race"]]}


def test_a_single_cohort_is_refused_for_a_measure_without_single_cohorts(published):
    with pytest.raises(SpecRefused) as refused:
        ask(with_single_cohorts(published), measure="dfw_rate", cohort="2022-23", group_by=["course"])
    assert refused.value.approved == {"cohorts": [COHORT]}


def test_an_unknown_filter_value_lists_the_values(published):
    with pytest.raises(SpecRefused) as refused:
        ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], where={"race": "Martian"})
    assert "Asian" in refused.value.approved["values"]["race"]


def test_more_than_three_dimensions_is_not_a_spec():
    with pytest.raises(ValidationError):
        Spec(measure="dfw_rate", cohort=COHORT, group_by=["course", "race", "gender", "pell"])


def test_a_long_answer_is_cut_at_the_cap(published):
    answer = ask(published, measure="dfw_rate", cohort=COHORT, group_by=["course"])
    assert (answer.row_count, answer.truncated) == (MAX_ROWS, True)


def test_a_results_file_changed_after_publishing_is_refused(published):
    _, results = published
    with sqlite3.connect(results) as connection:
        connection.execute("UPDATE success_measures SET metric_rate = 0.99 WHERE group_values = 'Asian'")
    with pytest.raises(SpecRefused, match="changed after it was published"):
        ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"])


def test_a_manifest_changed_after_publishing_is_refused(published):
    manifest, _ = published
    manifest.write_text(MANIFEST.replace("version: 2", "version: 3"), encoding="utf-8")
    with pytest.raises(SpecRefused, match="different manifest"):
        ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"])


def test_unpublished_results_are_refused(tmp_path):
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(MANIFEST, encoding="utf-8")
    with pytest.raises(SpecRefused, match="publish"):
        ResultsReader(manifest, tmp_path / "missing.sqlite").query(Spec(measure="gateway_math", cohort=COHORT, group_by=["race"]))


def test_min_denominator_drops_hidden_rows_and_small_groups(published):
    every_shown = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], min_denominator=1)
    assert [row.group["race"] for row in every_shown.rows] == ["Asian", "Black or African American"]
    large = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], min_denominator=121)
    assert [(row.group["race"], row.denominator) for row in large.rows] == [("Black or African American", 496)]
    exact = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], min_denominator=120)
    assert [row.group["race"] for row in exact.rows] == ["Asian", "Black or African American"]


def test_min_denominator_leaving_no_rows_is_an_answer_not_a_refusal(published):
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], where={"race": "Asian"},
                 min_denominator=500)
    assert (answer.rows, answer.row_count, answer.truncated) == ([], 0, False)


def test_min_denominator_must_be_positive():
    with pytest.raises(ValidationError):
        Spec(measure="gateway_math", cohort=COHORT, group_by=["race"], min_denominator=0)


def ranked(published):
    """Gender x race gap rows: two groups tied most behind, one behind less, one not compared."""
    add_rows(published,
             measures=[measure_row("gateway_math", "gender x race", "M x Asian", 0.2, 60),
                       measure_row("gateway_math", "gender x race", "F x Asian", 0.3, 60)],
             gaps=[("gateway_math", "gender x race", "M x Asian", "ok", -26.4),
                   ("gateway_math", "gender x race", "F x Black or African American", "ok", -3.0),
                   ("gateway_math", "gender x race", "F x Asian", "unknown_group", None)])


def test_rank_covers_the_whole_breakdown_even_when_where_narrows_the_rows(published):
    ranked(published)
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"], where={"gender": "F"},
                 include=["rates", "gaps"])
    by_race = {row.group["race"]: row for row in answer.rows}
    black = by_race["Black or African American"]
    assert (black.rank_in_breakdown, black.ranked_of) == (3, 3)
    # A group the gap finder didn't compare has a gap row but no rank.
    asian = by_race["Asian"]
    assert (asian.gap_status, asian.rank_in_breakdown, asian.ranked_of) == ("unknown_group", None, None)


def test_tied_groups_share_a_rank(published):
    ranked(published)
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"],
                 include=["rates", "gaps"])
    ranks = {tuple(row.group.values()): (row.rank_in_breakdown, row.ranked_of) for row in answer.rows}
    assert ranks == {("M", "Asian"): (1, 3), ("M", "Black or African American"): (1, 3),
                     ("F", "Black or African American"): (3, 3), ("F", "Asian"): (None, None)}
    assert answer.everyone.rank_in_breakdown is None


def test_ranks_are_left_out_without_gaps(published):
    ranked(published)
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"])
    assert {(row.rank_in_breakdown, row.ranked_of, row.gap_status) for row in answer.rows} == {(None, None, None)}


def test_max_rows_none_reads_every_row_and_the_default_stays_capped(published):
    manifest, results = published
    reader = ResultsReader(manifest, results)
    spec = Spec(measure="dfw_rate", cohort=COHORT, group_by=["course"])
    uncapped = reader.query(spec, max_rows=None)
    assert (uncapped.row_count, len(uncapped.rows), uncapped.truncated, uncapped.max_rows) == (
        MAX_ROWS + 5, MAX_ROWS + 5, False, None)
    capped = reader.query(spec)
    assert (capped.row_count, capped.truncated, capped.max_rows) == (MAX_ROWS, True, MAX_ROWS)
    assert capped.rows == uncapped.rows[:MAX_ROWS]
    assert reader.query(spec, max_rows=MAX_ROWS + 5).truncated is False
    assert reader.query(spec, max_rows=MAX_ROWS + 4).truncated is True


def test_max_rows_is_keyword_only(published):
    manifest, results = published
    with pytest.raises(TypeError):
        ResultsReader(manifest, results).query(Spec(measure="dfw_rate", cohort=COHORT, group_by=["course"]), None)


WILDCARD_COURSES = ["MATH_101", "MATHX101", "AID $1-2k", "50% OFF", "50X OFF", "A\\B", "A\\\\B"]


@pytest.mark.parametrize("course", ["MATH_101", "AID $1-2k", "50% OFF", "A\\B"])
def test_where_matches_values_holding_like_wildcards_literally(published, course):
    add_rows(published, measures=[measure_row("dfw_rate", "course", value, 0.2, 30) for value in WILDCARD_COURSES])
    answer = ask(published, measure="dfw_rate", cohort=COHORT, group_by=["course"], where={"course": course})
    assert [row.group["course"] for row in answer.rows] == [course]


def test_the_like_pattern_escapes_wildcards_so_sql_alone_cant_over_match(published):
    add_rows(published, measures=[measure_row("dfw_rate", "course", value, 0.2, 30) for value in WILDCARD_COURSES])
    _, results = published
    with sqlite3.connect(results) as connection:
        def found(pattern):
            return [row[0] for row in connection.execute(
                "SELECT group_values FROM success_measures WHERE group_values LIKE ? ESCAPE '\\'", (pattern,))]
        # Unescaped, _ and % match MATHX101 and 50X OFF too.
        assert sorted(found("MATH_101")) == ["MATHX101", "MATH_101"]
        assert found(like_pattern("course", {"course": "MATH_101"})) == ["MATH_101"]
        assert found(like_pattern("course", {"course": "50% OFF"})) == ["50% OFF"]
    assert like_pattern("gender x race", {"race": "Asian"}) == "% x Asian"


def test_where_is_exact_about_case_although_like_is_not(published):
    lower_case = measure_row("gateway_math", "gender x race", "m x Black or African American", 0.2, 40)
    add_rows(published, measures=[lower_case])
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["gender", "race"], where={"gender": "M"})
    assert [row.group["gender"] for row in answer.rows] == ["M"]


def test_a_where_value_too_long_for_like_is_not_a_spec():
    with pytest.raises(ValidationError):
        Spec(measure="dfw_rate", cohort=COHORT, group_by=["course"], where={"course": "x" * (MAX_VALUE_LENGTH + 1)})
    # SQLite refuses LIKE patterns over 50,000 bytes; the cap keeps every value far inside that.
    assert MAX_VALUE_LENGTH * 3 < 50_000

def test_a_missing_publication_record_says_to_load_the_model_first(published):
    """Publishing runs the measures against the loaded model, so the advice names both steps."""
    manifest, results = published
    publication_path(results).unlink()

    with pytest.raises(SpecRefused) as refused:
        ResultsReader(manifest, results).query(Spec(measure="gateway_math", cohort=COHORT, group_by=["race"]))

    message = str(refused.value)
    assert "python -m src.pipeline.run" in message and "python -m measures.publish" in message


def test_a_missing_results_file_gives_the_same_advice(published):
    manifest, results = published
    publication_path(results).unlink()
    results.unlink()

    with pytest.raises(SpecRefused) as refused:
        ResultsReader(manifest, results).query(Spec(measure="gateway_math", cohort=COHORT, group_by=["race"]))

    assert "python -m src.pipeline.run" in str(refused.value)



def statements(sql):
    """spec_sql's statements, without its comment lines."""
    body = "\n".join(line for line in sql.splitlines() if not line.startswith("--"))
    return [statement.strip() for statement in body.split(";") if statement.strip()]


def test_spec_sql_shows_the_measure_and_everyone_selects_with_values_written_in():
    sql = spec_sql(Spec(measure="gateway_math", cohort=COHORT, group_by=["race", "gender"]))
    assert sql.splitlines()[0] == (
        "-- Published results (python -m measures.publish): sqlite3 measures/output/success_measures.sqlite")
    measure, everyone = statements(sql)
    assert measure == (
        "SELECT group_values, status, numerator, denominator, metric_rate, note\n"
        "FROM success_measures\n"
        f"WHERE measure = 'gateway_math' AND cohort = '{COHORT}' AND group_dimensions = 'gender x race'\n"
        "ORDER BY group_values")
    assert everyone.endswith("AND group_dimensions = 'all'")
    # Nothing the spec didn't ask for.
    assert "LIKE" not in sql and "denominator >=" not in sql and "equity_gaps" not in sql and "?" not in sql


def test_spec_sql_adds_where_min_denominator_and_gaps_when_asked():
    sql = spec_sql(Spec(measure="dfw_rate", cohort=COHORT, group_by=["course"], where={"course": "MATH_101"},
                        min_denominator=25, include=["rates", "gaps"]))
    measure, gaps, everyone = statements(sql)
    assert "AND group_values LIKE 'MATH\\_101' ESCAPE '\\'" in measure
    assert "AND denominator >= 25\nORDER BY group_values" in measure
    assert gaps.startswith("SELECT group_values, status, gap_pts") and "FROM equity_gaps" in gaps
    assert "group_dimensions = 'course'" in gaps and "RANK() OVER compared" in gaps
    assert "exact matches of where" in sql and "200 rows" in sql


def test_spec_sql_doubles_single_quotes():
    sql = spec_sql(Spec(measure="dfw_rate", cohort=COHORT, group_by=["course"], where={"course": "O'Neil's ?"}))
    assert "LIKE 'O''Neil''s ?' ESCAPE" in sql


@pytest.mark.parametrize("spec", [
    {"group_by": ["race"]},
    {"group_by": ["gender", "race"], "where": {"race": "Black or African American"}},
    {"group_by": ["race"], "min_denominator": 100},
    {"group_by": ["gender", "race"], "include": ["rates", "gaps"]},
])
def test_spec_sql_run_on_the_file_finds_the_rows_the_builder_returns(published, spec):
    _, results = published
    full = Spec(measure="gateway_math", cohort=COHORT, **spec)
    answer = ask(published, **full.model_dump())
    measure, *rest = statements(spec_sql(full))
    with sqlite3.connect(results) as connection:
        found = connection.execute(measure).fetchall()
        everyone = connection.execute(rest[-1]).fetchone()
        for statement in rest[:-1]:
            connection.execute(statement).fetchall()   # the gaps SELECT runs as shown
    dimensions = " x ".join(sorted(full.group_by))
    assert [row[0] for row in found] == [" x ".join(row.group[name] for name in dimensions.split(" x "))
                                         for row in answer.rows]
    assert [row[3] for row in found] == [row.denominator for row in answer.rows]
    assert everyone[2] == answer.everyone.denominator


def with_trends(published, trends):
    """Add a measure_trends table holding trends (kpi, cohort, dimensions, values, previous, pct, direction,
    judgement, label), then publish the file again so the builder trusts it."""
    _, results = published
    with sqlite3.connect(results) as connection:
        connection.execute("CREATE TABLE measure_trends (kpi, cohort, previous_cohort, group_dimensions, group_values, "
                           "relative_pct, direction, judgement, label)")
        connection.executemany("INSERT INTO measure_trends VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                               [(kpi, cohort, previous, dims, values, pct, direction, judgement, label)
                                for kpi, cohort, dims, values, previous, pct, direction, judgement, label in trends])
    add_rows(published)
    return published


def test_trends_are_read_as_published_for_everyone_and_each_group(published):
    with_single_cohorts(published)
    with_trends(published, [
        ("gateway_math", "2022-23", "all", "all", "2021-22", -3.5, "down", "bad", "−3.5% vs 2021-22"),
        ("gateway_math", "2022-23", "race", "Asian", "2021-22", 10.0, "up", "good", "+10.0% vs 2021-22"),
    ])
    answer = ask(published, measure="gateway_math", cohort="2022-23", group_by=["race"], include=["rates", "trends"])
    assert (answer.everyone.trend_label, answer.everyone.trend_vs, answer.everyone.trend_pct) == (
        "−3.5% vs 2021-22", "2021-22", -3.5)
    asian = answer.rows[0]
    assert (asian.trend_direction, asian.trend_judgement, asian.trend_label) == ("up", "good", "+10.0% vs 2021-22")
    assert answer.entering_students_trend is None   # only the make-up measures carry it
    # Without trends asked for, the fields stay blank.
    plain = ask(published, measure="gateway_math", cohort="2022-23", group_by=["race"])
    assert plain.everyone.trend_label is None and plain.rows[0].trend_label is None


def test_a_pool_has_no_trend(published):
    with_trends(published, [])
    answer = ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], include=["rates", "trends"])
    assert answer.everyone.trend_label is None
    assert all(row.trend_label is None for row in answer.rows)


def test_trends_from_a_file_published_before_them_are_refused(published):
    with pytest.raises(SpecRefused, match="no trends"):
        ask(published, measure="gateway_math", cohort=COHORT, group_by=["race"], include=["trends"])


def test_the_trends_sql_is_shown_with_the_spec(published):
    sql = spec_sql(Spec(measure="transfer_in_share", cohort="2022-23", group_by=["race"], include=["rates", "trends"]))
    assert "FROM measure_trends" in sql
    assert "WHERE kpi = 'entering_students' AND cohort = '2022-23' AND group_dimensions = 'all'" in sql
