"""Checks the shared trend comparison and the completion measure on the tiny database (fixture.sql)."""
import sqlite3
from pathlib import Path

import pytest

from measures.compare import TREND_RULES, TrendRule, compare, compare_values
from measures.models import Cohort, Measure, Status
from measures.run_measures import run_measure

FIXTURE = Path(__file__).parent / "fixture.sql"


@pytest.fixture
def database():
    """The tiny database, in memory."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(FIXTURE.read_text(encoding="utf-8"))
    return connection


def everyone(database, measure, *years):
    """The everyone row of one measure for one cohort."""
    return next(r for r in run_measure(measure, [Cohort.of(*years)], database=database) if r.group.label == "everyone")


def test_a_rise_on_a_higher_is_better_kpi_is_good():
    change = compare_values("retention", 0.50, 0.55)
    assert (change.relative_pct, change.direction, change.judgement) == (10.0, "up", "good")


def test_a_fall_on_a_higher_is_better_kpi_is_bad():
    change = compare_values("retention", 0.50, 0.40)
    assert (change.relative_pct, change.direction, change.judgement) == (-20.0, "down", "bad")


def test_a_change_under_one_percent_reads_as_the_same():
    change = compare_values("completion", 0.500, 0.504)
    assert (change.direction, change.judgement) == ("flat", "neutral")


def test_a_rising_share_of_part_time_students_is_good():
    assert compare_values("part_time_share", 40.0, 60.0).judgement == "good"


def test_a_kpi_with_no_better_direction_is_never_judged(monkeypatch):
    monkeypatch.setitem(TREND_RULES, "unjudged", TrendRule(higher_is_better=None))
    assert compare_values("unjudged", 40.0, 60.0).judgement == "neutral"


@pytest.mark.parametrize("earlier, latest", [(None, 0.5), (0.5, None), (0, 0.5)])
def test_no_change_without_two_usable_numbers(earlier, latest):
    assert compare_values("retention", earlier, latest) is None


def test_compare_skips_a_hidden_row(database):
    shown = everyone(database, Measure.RETENTION, "2022-23")
    unseen = everyone(database, Measure.RETENTION, "2024-25")
    assert unseen.status == Status.NOT_YET_OBSERVABLE
    assert compare(shown, unseen) is None


def test_compare_refuses_two_measures(database):
    with pytest.raises(ValueError):
        compare(everyone(database, Measure.RETENTION, "2022-23"), everyone(database, Measure.PERSISTENCE, "2022-23"))


def test_completion_counts_awards_inside_the_window_once(database):
    row = everyone(database, Measure.COMPLETION, "2022-23")
    assert (row.numerator, row.denominator) == (9, 24)


def test_completion_waits_for_the_full_window(database):
    assert everyone(database, Measure.COMPLETION, "2023-24").status == Status.NOT_YET_OBSERVABLE


@pytest.mark.parametrize(
    "earlier, latest, label",
    [(0.50, 0.4825, "−3.5% vs 2022-23"), (0.50, 0.55, "+10.0% vs 2022-23"), (0.50, 0.5, "+0.0% vs 2022-23")],
)
def test_the_label_is_the_tiles_wording(earlier, latest, label):
    assert compare_values("retention", earlier, latest).label("2022-23") == label


def test_the_make_up_shares_count_every_entering_student(database):
    # 2022-23 in the fixture: students 1 to 24, two of them (23 and 24) transfer-in, none part-time.
    transfer = everyone(database, Measure.TRANSFER_IN_SHARE, "2022-23")
    part_time = everyone(database, Measure.PART_TIME_SHARE, "2022-23")
    entering = database.execute("SELECT COUNT(DISTINCT student_id) FROM cohort_membership WHERE cohort = '2022-23'").fetchone()[0]
    assert (transfer.numerator, transfer.denominator) == (2, entering)
    assert (part_time.numerator, part_time.denominator, part_time.n_excluded) == (0, entering, 0)
