"""Checks the measure calculations on a tiny database (fixture.sql).

Run from the repo root: python -m pytest measures/tests
"""
import sqlite3
from collections import defaultdict
from pathlib import Path

import pytest

from measures.calculations import midterm_alert, midterm_recovery
from measures.calculations.dfw import DFW_BELOW, ENROLLMENT_SQL, GRADE_REASONS, NOTE as DFW_NOTE, grade_outcomes, open_values
from measures.calculations.retention import STUDENT_SQL
from measures.calculations.sql_counts import count_in_sql
from measures.models import (
    ALLOWED_VALUES,
    EVERYONE,
    Cohort,
    Counts,
    ExclusionReason,
    Group,
    GroupBy,
    GroupDimension,
    Measure,
    MeasureResult,
    Status,
    UNKNOWN,
)
from measures.run_measures import (
    ACROSS_NOTE,
    COMPLEMENT_NOTE,
    MEASURES,
    NOISE_NOTE,
    build_result,
    groups_for,
    hidden_result,
    hide_across_cohorts,
    hide_complements,
    lines_by_key,
    read_open_values,
    run_measure,
)
from measures.save_results import CREATE_TABLE, save_results
from measures.tests.leaks import recoverable, weak_covers, worked_out

FIXTURE = Path(__file__).parent / "fixture.sql"

C2022 = Cohort.of("2022-23")


@pytest.fixture
def database():
    """The tiny database, in memory."""
    connection = sqlite3.connect(":memory:")
    connection.executescript(FIXTURE.read_text(encoding="utf-8"))
    return connection


def find(results, label):
    """The one row whose group has this label."""
    rows = [r for r in results if r.group.label == label]
    assert len(rows) == 1, label
    return rows[0]


def counted(database, measure, *dimensions):
    """The calculation's (numerator, denominator) per group label, before any group is hidden.

    For checking the arithmetic on groups the tiny database is too small to show.
    """
    group_by = [GroupBy.of(*dimensions)]
    groups = groups_for(group_by, read_open_values(database, MEASURES[measure], [C2022], group_by))
    counts = MEASURES[measure].count(database, [C2022], groups)
    return {group.label: (counts[(C2022, group)].numerator, counts[(C2022, group)].denominator) for group in groups}


def test_retention_for_everyone(database):
    row = find(run_measure(Measure.RETENTION, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (16, 20, 0.8)
    assert row.status == Status.OK
    assert (row.n_excluded, row.exclusion_reason) == (4, ExclusionReason.UNKNOWN_OUTCOME)
    assert row.exclusions == {ExclusionReason.UNKNOWN_OUTCOME: 4}
    assert row.n_out_of_scope == 0


def test_persistence_for_everyone(database):
    row = find(run_measure(Measure.PERSISTENCE, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (5, 20, 0.25)


def test_small_group_is_hidden_by_students_counted(database):
    # 12 students are pell = N, but only 8 have an answer, so the group is hidden.
    results = run_measure(Measure.RETENTION, [C2022], [GroupBy.of(GroupDimension.PELL)], database=database)
    assert counted(database, Measure.RETENTION, GroupDimension.PELL)["pell=Y"] == (12, 12)
    # pell = Y is hidden too, or everyone minus pell = Y would give pell = N.
    assert find(results, "pell=Y").status == Status.SUPPRESSED
    assert find(results, "pell=Y").note.endswith(COMPLEMENT_NOTE)

    hidden = find(results, "pell=N")
    assert hidden.status == Status.SUPPRESSED and hidden.suppressed
    assert hidden.numerator is None and hidden.denominator is None and hidden.metric_rate is None
    assert hidden.n_excluded is None


def test_group_values_match_ignoring_case_and_spaces(database):
    # The data says FALL and ">20 - 24". The groups say Fall and "> 20-24".
    assert counted(database, Measure.RETENTION, GroupDimension.COHORT_TERM)["cohort_term=Fall"] == (14, 14)
    assert counted(database, Measure.RETENTION, GroupDimension.AGE_BAND)["age_band=> 20-24"][1] == 12


def test_two_way_group(database):
    results = run_measure(
        Measure.RETENTION, [C2022], [GroupBy.of(GroupDimension.PELL, GroupDimension.COHORT_TERM)], database=database
    )
    assert counted(database, Measure.RETENTION, GroupDimension.PELL, GroupDimension.COHORT_TERM)["cohort_term=Fall, pell=Y"][1] == 12
    # Fall, pell = N is hidden, so Fall, pell = Y is hidden too, or the Fall total minus it would give pell = N.
    assert find(results, "cohort_term=Fall, pell=Y").note.endswith(COMPLEMENT_NOTE)
    # No pell = Y students started in spring, so that group is empty and hidden.
    assert find(results, "cohort_term=Spring, pell=Y").status == Status.SUPPRESSED


def test_pooled_cohort_counts_both_years_together(database):
    row = find(run_measure(Measure.RETENTION, [Cohort.of("2022-23", "2023-24")], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (22, 32, 0.6875)


def test_cohort_with_no_answers_is_not_yet_observable(database):
    row = find(run_measure(Measure.RETENTION, [Cohort.of("2024-25")], database=database), "everyone")
    assert row.status == Status.NOT_YET_OBSERVABLE and row.suppressed


@pytest.mark.parametrize("dimension", list(ALLOWED_VALUES))  # the dimensions with a fixed list of values
def test_groups_of_a_dimension_add_up_to_everyone(database, dimension):
    # Blank and unlisted values (pell 'U', a blank enrollment type, every first gen) count as UNKNOWN.
    cohort = Cohort.of("2022-23", "2023-24", "2024-25")
    groups = [EVERYONE] + [Group.of((dimension, value)) for value in ALLOWED_VALUES[dimension]]
    counts = count_in_sql(database, STUDENT_SQL, [cohort], groups)

    students = {group: counts[(cohort, group)].denominator + counts[(cohort, group)].n_excluded for group in groups}
    assert students[EVERYONE] == 48
    assert sum(n for group, n in students.items() if group != EVERYONE) == 48


def test_pooling_a_year_with_no_answers_is_not_yet_observable(database):
    # 2023-24 has answers, but 2024-25 doesn't, so the pool can't be read yet.
    row = find(run_measure(Measure.RETENTION, [Cohort.of("2023-24", "2024-25")], database=database), "everyone")
    assert row.status == Status.NOT_YET_OBSERVABLE


def test_no_cohorts_is_an_error(database):
    with pytest.raises(ValueError):
        run_measure(Measure.RETENTION, [], database=database)


def test_every_measure_has_a_calculation():
    assert set(MEASURES) == set(Measure)


def test_gateway_counts_every_required_student(database):
    # Students 17-20 were required but never took math. They count as not completed.
    row = find(run_measure(Measure.GATEWAY_MATH, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (12, 20, 0.6)


def test_gateway_reports_unclassified_and_not_required_students_apart(database):
    # Student 23's requirement is unknown and 24 is required with no outcome: left out. 21 and 22 aren't required: out of scope.
    row = find(run_measure(Measure.GATEWAY_MATH, [C2022], database=database), "everyone")
    assert (row.n_excluded, row.exclusion_reason) == (2, ExclusionReason.UNKNOWN_REQUIREMENT_OR_OUTCOME)
    assert row.exclusions == {ExclusionReason.UNKNOWN_REQUIREMENT_OR_OUTCOME: 2}
    assert row.n_out_of_scope == 2


def test_gateway_english(database):
    row = find(run_measure(Measure.GATEWAY_ENGLISH, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator) == (10, 24)
    assert (row.n_excluded, row.exclusion_reason, row.n_out_of_scope) == (0, None, 0)


def test_gateway_group_is_hidden_by_students_counted(database):
    # 12 students are pell = N, but 2 aren't required and 2 can't be classified, so only 8 are counted and the group is hidden.
    results = run_measure(Measure.GATEWAY_MATH, [C2022], [GroupBy.of(GroupDimension.PELL)], database=database)
    assert counted(database, Measure.GATEWAY_MATH, GroupDimension.PELL)["pell=Y"] == (12, 12)
    assert find(results, "pell=Y").status == Status.SUPPRESSED  # cover for pell = N

    hidden = find(results, "pell=N")
    assert hidden.status == Status.SUPPRESSED
    assert hidden.numerator is None and hidden.denominator is None
    assert hidden.n_excluded is None and hidden.n_out_of_scope is None


def test_gateway_pooled_cohort(database):
    # 12 of 20 in 2022-23 and 6 of 12 in 2023-24.
    row = find(run_measure(Measure.GATEWAY_MATH, [Cohort.of("2022-23", "2023-24")], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (18, 32, 0.5625)
    assert row.n_out_of_scope == 2


def test_gateway_cohort_with_no_answers_is_not_yet_observable(database):
    row = find(run_measure(Measure.GATEWAY_MATH, [Cohort.of("2024-25")], database=database), "everyone")
    assert row.status == Status.NOT_YET_OBSERVABLE


def test_dfw_counts_enrollments_with_a_final_grade(database):
    row = find(run_measure(Measure.DFW_RATE, [C2022], database=database), "everyone")
    # 27 enrollments with a class. Incomplete and audit are left out, and so is the row with no class.
    assert (row.numerator, row.denominator, row.metric_rate) == (10, 25, 0.4)
    # Student 22's grade is incomplete and 23 audited. Each is left out for its own reason.
    assert row.n_excluded == 2
    assert row.exclusions == {ExclusionReason.INCOMPLETE: 1, ExclusionReason.AUDIT: 1}
    assert row.exclusion_reason == ExclusionReason.INCOMPLETE  # a tie goes to the reason listed first
    assert (row.n_out_of_scope, row.status) == (0, Status.OK)


def test_dfw_groups_split_the_enrollments(database):
    results = run_measure(Measure.DFW_RATE, [C2022], [GroupBy.of(GroupDimension.PELL)], database=database)
    assert (find(results, "pell=Y").numerator, find(results, "pell=Y").denominator) == (3, 15)
    assert (find(results, "pell=N").numerator, find(results, "pell=N").denominator) == (7, 10)


def test_dfw_cohort_with_no_final_grades_is_not_yet_observable(database):
    row = find(run_measure(Measure.DFW_RATE, [Cohort.of("2024-25")], database=database), "everyone")
    assert row.status == Status.NOT_YET_OBSERVABLE


def test_dfw_group_is_hidden_by_students_counted(database):
    # 2023-24 has 12 graded enrollments, but they come from only 3 students, so the group is hidden.
    row = find(run_measure(Measure.DFW_RATE, [Cohort.of("2023-24")], database=database), "everyone")
    assert row.status == Status.SUPPRESSED
    assert row.numerator is None and row.denominator is None and row.n_excluded is None


def test_dfw_pooled_cohort(database):
    # 10 of 25 in 2022-23 and 0 of 12 in 2023-24.
    row = find(run_measure(Measure.DFW_RATE, [Cohort.of("2022-23", "2023-24")], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (10, 37, 0.2703)


def test_dfw_every_grade_that_is_left_out_has_a_reason():
    classified = grade_outcomes()
    # A grade is either classified or explained, never both.
    assert not set(GRADE_REASONS) & set(classified)
    assert GRADE_REASONS["I"] == ExclusionReason.INCOMPLETE and GRADE_REASONS["A"] == ExclusionReason.AUDIT
    assert GRADE_REASONS["OTH"] == GRADE_REASONS["O"] == ExclusionReason.OTHER_GRADE


def test_exclusions_must_add_up_and_a_hidden_row_has_none():
    row = shown_row(n_excluded=4, exclusions={ExclusionReason.INCOMPLETE: 3, ExclusionReason.AUDIT: 1})
    MeasureResult(**row)
    with pytest.raises(ValueError):
        MeasureResult(**shown_row(exclusions={}))  # 4 left out, but no reasons given
    with pytest.raises(ValueError):
        MeasureResult(**shown_row(n_excluded=4, exclusions={ExclusionReason.INCOMPLETE: 3}))
    with pytest.raises(ValueError):
        MeasureResult(**shown_row(n_excluded=4, exclusions={ExclusionReason.INCOMPLETE: 4, ExclusionReason.AUDIT: 0}))
    with pytest.raises(ValueError):
        MeasureResult(**shown_row(
            numerator=None, denominator=None, metric_rate=None, status=Status.SUPPRESSED,
            n_excluded=None, n_out_of_scope=None, exclusion_reason=None, exclusions={ExclusionReason.AUDIT: 1},
        ))


def test_saving_into_a_file_from_before_exclusions_existed(database, tmp_path):
    target = tmp_path / "old.sqlite"
    older_table = CREATE_TABLE.replace("    exclusions       TEXT,\n", "")
    assert "exclusions" not in older_table
    old = sqlite3.connect(target)
    old.execute(older_table)
    old.commit()
    old.close()

    save_results(run_measure(Measure.DFW_RATE, [C2022], database=database), "test load", target)
    saved = sqlite3.connect(target).execute("SELECT exclusions FROM success_measures WHERE group_values = 'all'").fetchone()
    assert saved == ('{"audit": 1, "incomplete": 1}',)


def test_exclusions_are_saved_as_text(database, tmp_path):
    results = run_measure(Measure.DFW_RATE, [C2022], database=database)
    target = tmp_path / "results.sqlite"
    save_results(results, "test load", target)
    saved = sqlite3.connect(target).execute("SELECT exclusions FROM success_measures WHERE group_values = 'all'").fetchone()
    assert saved == ('{"audit": 1, "incomplete": 1}',)


def test_dfw_by_course_finds_the_courses_in_the_data(database):
    results = run_measure(Measure.DFW_RATE, [C2022], [GroupBy.of(GroupDimension.COURSE)], database=database)
    # Only the courses with an enrollment in 2022-23 get a row. The courses come from the data, not a list.
    assert sorted(r.group.label for r in results) == ["course=ENGL 1302", "course=MATH 1314", "everyone"]

    assert counted(database, Measure.DFW_RATE, GroupDimension.COURSE)["course=ENGL 1302"] == (7, 22)
    # Three students took MATH 1314, so it is hidden for size. Its DFW denominator is above 0, so it needs cover,
    # and ENGL 1302 is hidden as its cover.
    assert find(results, "course=MATH 1314").status == Status.SUPPRESSED
    assert find(results, "course=ENGL 1302").status == Status.SUPPRESSED


def test_dfw_by_course_and_pell(database):
    counts = counted(database, Measure.DFW_RATE, GroupDimension.COURSE, GroupDimension.PELL)
    assert counts["course=ENGL 1302, pell=Y"] == (0, 12)
    assert counts["course=ENGL 1302, pell=N"] == (7, 10)


def test_only_course_measures_can_be_grouped_by_course(database):
    with pytest.raises(ValueError):
        run_measure(Measure.RETENTION, [C2022], [GroupBy.of(GroupDimension.COURSE)], database=database)
    with pytest.raises(ValueError):
        run_measure(Measure.MIDTERM_RECOVERY_RATE, [C2022], [GroupBy.of(GroupDimension.COURSE)], database=database)


def test_a_course_can_be_any_text_but_not_blank():
    Group.of((GroupDimension.COURSE, "ENGL 1302"))
    with pytest.raises(ValueError):
        Group.of((GroupDimension.COURSE, "  "))


def add_student(database, student_id, cohort):
    """A student in a cohort of their own, so their enrollments can be counted apart from the fixture's."""
    database.execute("INSERT INTO student VALUES (?, 'Older than 24', 'White', 'N', 'F', NULL)", (student_id,))
    database.execute(
        "INSERT INTO cohort_membership (student_id, cohort, cohort_term, enrollment_type, enrollment_intensity_first_term,"
        " pell_status_first_year) VALUES (?, ?, 'FALL', 'First-time', 'Full-time', 'Y')",
        (student_id, cohort),
    )


def test_dfw_grades_match_ignoring_case_spaces_and_decimals(database):
    add_student(database, "t1", "2025-26")
    for grade in (" w ", "1.67", "4.00", "f", "3.67", "ABC"):
        database.execute("INSERT INTO course_enrollment (student_id, cohort, course_id, grade) VALUES ('t1', '2025-26', 1, ?)", (grade,))
    cohort = Cohort.of("2025-26")

    counts = count_in_sql(database, ENROLLMENT_SQL, [cohort], [EVERYONE])[(cohort, EVERYONE)]
    # A withdrawal, 1.67 and an F are D, F or W. 4.00 and 3.67 passed. ABC isn't a grade we know.
    assert (counts.numerator, counts.denominator, counts.n_excluded) == (3, 5, 1)
    assert counts.exclusions == {ExclusionReason.UNLISTED_GRADE: 1}


def test_dfw_courses_that_differ_only_in_case_are_one_course(database):
    add_student(database, "t1", "2025-26")
    database.execute("INSERT INTO course VALUES (5, 'ENG', '101')")
    database.execute("INSERT INTO course VALUES (6, 'eng', '101')")
    database.execute("INSERT INTO course_enrollment (student_id, cohort, course_id, grade) VALUES ('t1', '2025-26', 5, 'P')")
    database.execute("INSERT INTO course_enrollment (student_id, cohort, course_id, grade) VALUES ('t1', '2025-26', 6, 'F')")
    cohort = Cohort.of("2025-26")

    assert open_values(database, GroupDimension.COURSE, [cohort]) == ["ENG 101"]
    group = Group.of((GroupDimension.COURSE, "ENG 101"))
    counts = count_in_sql(database, ENROLLMENT_SQL, [cohort], [group])[(cohort, group)]
    assert (counts.numerator, counts.denominator) == (1, 2)


def test_dfw_note_follows_the_cutoff():
    assert f"under {DFW_BELOW:.1f}" in DFW_NOTE


def test_dfw_grade_rules():
    outcomes = grade_outcomes()
    # Below 2.0 is a D or F, written either way. Passing numbers, P, and a failing or withdrawn code are classified.
    assert outcomes["1.9"] and outcomes["1"] and outcomes["1.0"] and outcomes["0"]
    assert not outcomes["2"] and not outcomes["2.0"] and not outcomes["4.0"] and not outcomes["P"]
    assert outcomes["F"] and outcomes["W"]
    # Grade points to two decimals, as an institution's own file may write them.
    assert outcomes["1.67"] and not outcomes["3.67"] and not outcomes["4.00"] and outcomes["0.07"]
    # Incomplete, audit, missing and other grades, and anything unknown, have no outcome and are left out.
    for left_out in ("I", "A", "M", "O", "OTH", "UNKNOWN", "UW"):
        assert left_out not in outcomes


def test_credit_completion_averages_each_students_ratio(database):
    row = find(run_measure(Measure.CREDIT_COMPLETION, [C2022], database=database), "everyone")
    # 10 students at 1.0, 6 at 0 and 2 at 0.5 add up to 11 over 18 students. Pooling credits would give 162 / 192 = 0.84.
    assert (row.numerator, row.denominator, row.metric_rate) == (11, 18, 0.6111)
    assert row.status == Status.OK


def test_credit_completion_reports_left_out_students_by_reason(database):
    row = find(run_measure(Measure.CREDIT_COMPLETION, [C2022], database=database), "everyone")
    # 17-18 have no credits recorded, 19 attempted none, 20's full- or part-time status is unknown.
    assert row.exclusions == {
        ExclusionReason.UNKNOWN_OUTCOME: 2,
        ExclusionReason.NO_CREDITS_ATTEMPTED: 1,
        ExclusionReason.UNKNOWN_ATTENDANCE_TYPE: 1,
    }
    assert (row.n_excluded, row.exclusion_reason) == (4, ExclusionReason.UNKNOWN_OUTCOME)
    # 21-22 are re-admits, so the measure doesn't apply to them.
    assert row.n_out_of_scope == 2


def test_credit_completion_groups(database):
    results = run_measure(Measure.CREDIT_COMPLETION, [C2022], [GroupBy.of(GroupDimension.PELL)], database=database)
    assert counted(database, Measure.CREDIT_COMPLETION, GroupDimension.PELL)["pell=Y"] == (10, 12)
    # pell = N has only 6 students counted, so it is hidden.
    assert find(results, "pell=N").status == Status.SUPPRESSED


def test_credit_completion_by_enrollment_type(database):
    results = run_measure(Measure.CREDIT_COMPLETION, [C2022], [GroupBy.of(GroupDimension.ENROLLMENT_TYPE)], database=database)
    assert counted(database, Measure.CREDIT_COMPLETION, GroupDimension.ENROLLMENT_TYPE)["enrollment_type=First-time"] == (10, 16)
    assert find(results, "enrollment_type=Transfer-in").status == Status.SUPPRESSED  # 2 students
    assert find(results, "enrollment_type=Re-admit").status == Status.SUPPRESSED  # nobody is counted
    # Re-admit is no cover, so First-time is hidden too: everyone minus it would give Transfer-in.
    assert find(results, "enrollment_type=First-time").note.endswith(COMPLEMENT_NOTE)


def test_credit_completion_pooled_cohort(database):
    # 11 / 18 in 2022-23 and 6 / 12 in 2023-24.
    row = find(run_measure(Measure.CREDIT_COMPLETION, [Cohort.of("2022-23", "2023-24")], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (17, 30, 0.5667)


def test_credit_completion_cohort_with_no_credits_is_not_yet_observable(database):
    row = find(run_measure(Measure.CREDIT_COMPLETION, [Cohort.of("2024-25")], database=database), "everyone")
    assert row.status == Status.NOT_YET_OBSERVABLE


def test_credit_completion_ratio_is_kept_at_one(database):
    # Student 1 earned 20 of 15 attempted credits. The ratio stays at 1, so the numerator can't pass the denominator.
    database.execute("UPDATE cohort_membership SET number_of_credits_earned_yr_1 = 20 WHERE student_id = 's01'")
    row = find(run_measure(Measure.CREDIT_COMPLETION, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator) == (11, 18)


def test_credit_completion_leaves_out_blank_and_unknown_enrollment_types(database):
    # Only first-time and transfer-in are counted. A blank or UNKNOWN type can't be told apart, so it is left out with its own reason.
    database.execute("UPDATE cohort_membership SET enrollment_type = NULL WHERE student_id = 's02'")
    database.execute("UPDATE cohort_membership SET enrollment_type = 'UNKNOWN' WHERE student_id = 's03'")
    row = find(run_measure(Measure.CREDIT_COMPLETION, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator) == (9, 16)
    assert row.exclusions[ExclusionReason.UNKNOWN_ENROLLMENT_TYPE] == 2
    assert row.n_excluded == 6 and row.n_out_of_scope == 2


def test_credit_completion_needs_at_least_one_credit_attempted(database):
    # Half a credit is below the minimum of 1, so student 5 is left out, not counted.
    database.execute(
        "UPDATE cohort_membership SET number_of_credits_attempted_yr_1 = 0.5, number_of_credits_earned_yr_1 = 0.5 WHERE student_id = 's05'"
    )
    row = find(run_measure(Measure.CREDIT_COMPLETION, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator) == (10, 17)
    assert row.exclusions[ExclusionReason.NO_CREDITS_ATTEMPTED] == 2


def test_results_are_saved_and_replaced(database, tmp_path):
    results = run_measure(Measure.RETENTION, [C2022], [GroupBy.of(GroupDimension.PELL)], database=database)
    target = tmp_path / "results.sqlite"

    save_results(results, "test load", target)
    save_results(results, "test load", target)  # saving again replaces rows, it doesn't add them

    saved = sqlite3.connect(target)
    assert saved.execute("SELECT COUNT(*) FROM success_measures").fetchone() == (len(results),)
    row = saved.execute(
        "SELECT numerator, denominator, status FROM success_measures WHERE group_values = 'N'"
    ).fetchone()
    assert row == (None, None, "suppressed")


def test_a_save_is_always_the_latest_run(database, tmp_path):
    by_pell = run_measure(Measure.RETENTION, [C2022], [GroupBy.of(GroupDimension.PELL)], database=database)
    plain = run_measure(Measure.RETENTION, [C2022], database=database)
    persistence = run_measure(Measure.PERSISTENCE, [C2022], database=database)
    target = tmp_path / "results.sqlite"
    saved = sqlite3.connect(target)

    def count_rows(measure):
        return saved.execute("SELECT COUNT(*) FROM success_measures WHERE measure = ?", (measure,)).fetchone()[0]

    save_results(by_pell, "load 1", target)
    save_results(plain, "load 2", target)  # the by-Pell rows must not stay behind
    assert count_rows("retention") == len(plain)
    assert saved.execute("SELECT DISTINCT data_loaded_at FROM success_measures").fetchall() == [("load 2",)]

    # Saving another measure leaves retention alone.
    save_results(persistence, "load 2", target)
    assert count_rows("retention") == len(plain) and count_rows("persistence") == len(persistence)


def shown_row(**changes):
    """A valid shown row. Pass changes to break one rule."""
    row = dict(
        measure=Measure.RETENTION, cohort=C2022, group=EVERYONE, numerator=16, denominator=20,
        metric_rate=0.8, status=Status.OK, n_excluded=4, n_out_of_scope=0,
        exclusion_reason=ExclusionReason.UNKNOWN_OUTCOME, note="n", exclusions={ExclusionReason.UNKNOWN_OUTCOME: 4},
    )
    return {**row, **changes}


def test_a_shown_row_is_checked_against_its_own_numbers():
    MeasureResult(**shown_row())
    with pytest.raises(ValueError):
        MeasureResult(**shown_row(numerator=21))  # more than the denominator
    with pytest.raises(ValueError):
        MeasureResult(**shown_row(metric_rate=0.75))  # not numerator / denominator


def test_suppressed_follows_the_status():
    hidden = dict(
        numerator=None, denominator=None, metric_rate=None, n_excluded=None, n_out_of_scope=None,
        exclusion_reason=None, exclusions={},
    )
    assert not MeasureResult(**shown_row()).suppressed
    assert MeasureResult(**shown_row(**hidden, status=Status.SUPPRESSED)).suppressed
    assert MeasureResult(**shown_row(**hidden, status=Status.NOT_YET_OBSERVABLE)).suppressed


RACES = ["Asian", "Black or African American", "Hispanic", "White"]


# A group whose students are all out of scope: nobody in it is counted in the measure.
OUT_OF_SCOPE_ONLY = Counts(numerator=0, denominator=0, n_students=0, n_out_of_scope=3)


def as_counts(size):
    """Counts for a group of size students, half of them retained, or size itself when it is already Counts."""
    if isinstance(size, Counts):
        return size
    return Counts(numerator=size // 2, denominator=size, n_students=size)


def hide(groups, sizes):
    """Retention rows for everyone and these groups after hide_complements. Each size is students or Counts."""
    all_counts = {(C2022, g): as_counts(size) for g, size in zip(groups, sizes)}
    parts = all_counts.values()
    all_counts[(C2022, EVERYONE)] = Counts(
        numerator=sum(c.numerator for c in parts),
        denominator=sum(c.denominator for c in parts),
        n_students=sum(c.n_students for c in parts),
    )
    results = [build_result(Measure.RETENTION, C2022, g, all_counts[(C2022, g)], "note.") for g in [EVERYONE, *groups]]
    return hide_complements(results, all_counts)


def race_breakdown(*sizes):
    """Retention rows for everyone and one race group per size, after hide_complements."""
    return hide([Group.of((GroupDimension.RACE, race)) for race in RACES[: len(sizes)]], sizes)


def gender_by_race(sizes):
    """Retention rows for a gender x race table after hide_complements. sizes maps (gender, race) to a size."""
    return hide([Group.of((GroupDimension.GENDER, g), (GroupDimension.RACE, r)) for g, r in sizes], list(sizes.values()))


def hidden_pairs(results):
    """The (gender, race) pairs whose rows are hidden."""
    pairs = set()
    for r in results:
        if r.group.parts and r.suppressed:
            values = {p.dimension: p.value for p in r.group.parts}
            pairs.add((values[GroupDimension.GENDER], values[GroupDimension.RACE]))
    return pairs


def test_a_lone_hidden_pair_is_covered_in_its_row_and_column():
    # Men, Hispanic (5) is alone in the men's row. Hiding men, Black then leaves women, Black alone in its column,
    # and the cover for that is women, Hispanic, whose column already hides someone: a rectangle of four.
    sizes = {
        ("M", "Asian"): 50, ("M", "Black or African American"): 40, ("M", "Hispanic"): 5,
        ("F", "Asian"): 50, ("F", "Black or African American"): 50, ("F", "Hispanic"): 50,
    }
    hidden = hidden_pairs(gender_by_race(sizes))
    # Four pairs in two races, for both genders: every row and column then hides two or none.
    assert ("M", "Hispanic") in hidden and len(hidden) == 4
    assert len({race for _, race in hidden}) == 2 and {gender for gender, _ in hidden} == {"M", "F"}


def test_two_hidden_pairs_in_one_row_and_column_need_no_more_cover():
    sizes = {("M", "Asian"): 5, ("M", "Hispanic"): 4, ("F", "Asian"): 3, ("F", "Hispanic"): 6, ("M", "White"): 50, ("F", "White"): 50}
    assert hidden_pairs(gender_by_race(sizes)) == {("M", "Asian"), ("M", "Hispanic"), ("F", "Asian"), ("F", "Hispanic")}


@pytest.mark.parametrize(
    "dimensions",
    [(GroupDimension.PELL, GroupDimension.COHORT_TERM), (GroupDimension.GENDER, GroupDimension.RACE), (GroupDimension.COURSE, GroupDimension.PELL)],
)
def test_no_line_of_a_two_way_breakdown_has_one_hidden_group(database, dimensions):
    # Hold one dimension fixed and the rest of the line adds up to a total, so it must never hide exactly one group.
    measure = Measure.DFW_RATE if GroupDimension.COURSE in dimensions else Measure.RETENTION
    results = run_measure(measure, [C2022], [GroupBy.of(*dimensions)], database=database)
    if find(results, "everyone").suppressed:
        return
    counts = counted(database, measure, *dimensions)
    for fixed in dimensions:
        lines = {}
        for r in results:
            if r.group.parts:
                key = next(p.value for p in r.group.parts if p.dimension == fixed)
                lines.setdefault(key, []).append(r)
        for key, line in lines.items():
            hidden = [r for r in line if r.suppressed and counts[r.group.label][1] > 0]
            shown = [r for r in line if not r.suppressed]
            assert len(hidden) != 1 or not shown, (fixed.value, key)


def test_a_deeper_line_is_checked_only_when_its_total_is_in_the_run():
    # Course x gender x race: holding gender and race fixed, the courses add up to that gender x race pair.
    # Holding course fixed, they add up to course x race or course x gender, which nothing here publishes.
    parts = [(GroupDimension.COURSE, "ENGL 1302"), (GroupDimension.RACE, "Asian")]
    three_way = [Group.of(*parts, (GroupDimension.GENDER, gender)) for gender in ("M", "F")]
    pair = Group.of((GroupDimension.GENDER, "M"), (GroupDimension.RACE, "Asian"))

    def deeper_lines(groups, size):
        """The three-way groups' lines, by the dimension each varies, when every group has size students."""
        rows = {(C2022, EVERYONE): build_result(Measure.DFW_RATE, C2022, EVERYONE, as_counts(100), "note.")}
        for g in groups:
            rows[(C2022, g)] = build_result(Measure.DFW_RATE, C2022, g, as_counts(size), "note.")
        lines, _ = lines_by_key(rows)
        return {key[2]: line for key, line in lines.items() if len(key[1]) == 3}

    assert deeper_lines(three_way, 20) == {}
    # Shown or hidden, the pair is in the run, so it is in the line of the courses that add up to it.
    for size in (20, 5):
        lines = deeper_lines([*three_way, pair], size)
        assert set(lines) == {GroupDimension.COURSE}
        assert lines[GroupDimension.COURSE] == [three_way[0], pair]


def hidden_races(results):
    """The races whose rows are hidden."""
    return {next(iter(r.group.parts)).value for r in results if r.group.parts and r.suppressed}


def test_a_lone_hidden_group_gets_the_next_smallest_hidden_too():
    # Planted 50 / 40 / 5: everyone minus 50 minus 40 would give the 5, so the 40 is hidden as well.
    results = race_breakdown(50, 40, 5)
    assert hidden_races(results) == {"Black or African American", "Hispanic"}
    assert find(results, "race=Black or African American").note == "note." + COMPLEMENT_NOTE
    assert find(results, "everyone").status == Status.OK


def test_two_hidden_groups_need_no_more_cover():
    assert hidden_races(race_breakdown(50, 5, 4)) == {"Black or African American", "Hispanic"}


def test_an_empty_hidden_group_is_no_cover():
    # The 0 and the 5 are hidden, but 0 hides nobody, so the 5 is still alone and the 40 covers it.
    assert hidden_races(race_breakdown(50, 40, 5, 0)) == {"Black or African American", "Hispanic", "White"}


def test_an_out_of_scope_only_group_is_no_cover():
    # Its students add 0 to the numerator and denominator, so the 5 is still alone and the 40 covers it.
    assert hidden_races(race_breakdown(50, 40, 5, OUT_OF_SCOPE_ONLY)) == {"Black or African American", "Hispanic", "White"}


def test_an_out_of_scope_only_group_needs_no_cover():
    # Subtraction gives it 0 / 0, which it is: nothing to protect, so the 40 stays shown.
    results = race_breakdown(50, 40, OUT_OF_SCOPE_ONLY)
    assert hidden_races(results) == {"Hispanic"}
    assert find(results, "race=Black or African American").status == Status.OK


def test_an_out_of_scope_only_pair_is_no_cover_in_a_two_way_table():
    # Like credit completion's Native Hawaiian or Other Pacific Islander column: men 9, women 12, and an UNKNOWN
    # gender pair whose students are all out of scope. The race total minus women would give the men's 9.
    # The men are in no other race, so only this column can protect them.
    nhpi = "Native Hawaiian or Other Pacific Islander"
    sizes = {("M", nhpi): 9, ("F", nhpi): 12, (UNKNOWN, nhpi): OUT_OF_SCOPE_ONLY, ("F", "Asian"): 50, ("F", "White"): 50}
    hidden = hidden_pairs(gender_by_race(sizes))
    assert {("M", nhpi), ("F", nhpi)} <= hidden


def test_nothing_hidden_changes_nothing():
    assert hidden_races(race_breakdown(50, 40)) == set()


@pytest.mark.parametrize("measure", list(MEASURES))
@pytest.mark.parametrize("dimension", list(ALLOWED_VALUES))
def test_no_hidden_group_can_be_worked_out_by_subtraction(database, measure, dimension):
    # Everyone minus the shown groups must never be a single hidden group that anyone is counted in.
    results = run_measure(measure, [C2022], [GroupBy.of(dimension)], database=database)
    if find(results, "everyone").suppressed:
        return
    counts = counted(database, measure, dimension)
    hidden = [r for r in results if r.group.parts and r.suppressed and counts[r.group.label][1] > 0]
    assert len(hidden) != 1, hidden[0].group.label if hidden else None


# Hiding across a pooled cohort and its single years.
C2023 = Cohort.of("2023-24")
POOL = Cohort.of("2022-23", "2023-24")


def summed(counts):
    """One Counts adding up several: everyone in a year, or a pooled cohort's group."""
    return Counts(
        numerator=sum(c.numerator for c in counts),
        denominator=sum(c.denominator for c in counts),
        n_students=sum(c.n_students for c in counts),
        n_out_of_scope=sum(c.n_out_of_scope for c in counts),
    )


def pooled_by_race(sizes, years=(C2022, C2023), covers=()):
    """Race rows for the 2022-23 + 2023-24 pool and these years after both hiding passes, by (cohort, race).

    sizes maps each year to one size per race (students or Counts); the pool's counts are their sums.
    covers are (cohort, race) rows hidden before hide_across_cohorts, as hide_complements might have.
    Returns (rows before hide_across_cohorts, rows after).
    """
    before, after, _ = pooled_run(sizes, years, covers)
    return by_race(before), by_race(after)


def pooled_run(sizes, years=(C2022, C2023), covers=()):
    """pooled_by_race's rows as lists, everyone included, with the counts: (before, after, all_counts)."""
    races = [Group.of((GroupDimension.RACE, race)) for race in RACES]
    all_counts = {}
    for year in (C2022, C2023):
        for group, size in zip(races, sizes[year]):
            all_counts[(year, group)] = as_counts(size)
        all_counts[(year, EVERYONE)] = summed([all_counts[(year, g)] for g in races])
    for group in [EVERYONE, *races]:
        all_counts[(POOL, group)] = summed([all_counts[(year, group)] for year in (C2022, C2023)])
    results = [
        build_result(Measure.RETENTION, cohort, g, all_counts[(cohort, g)], "note.")
        for cohort in (POOL, *years) for g in [EVERYONE, *races]
    ]
    results = hide_complements(results, all_counts)
    for cohort, race in covers:
        index = next(i for i, r in enumerate(results) if (r.cohort, r.group.label) == (cohort, f"race={race}"))
        results[index] = hidden_result(Measure.RETENTION, cohort, results[index].group, Status.SUPPRESSED, "note.")
    after = hide_across_cohorts(results, all_counts)
    return results, after, all_counts


def by_race(results):
    """Rows by (cohort, race), leaving out everyone."""
    return {(r.cohort, next(iter(r.group.parts)).value): r for r in results if r.group.parts}


def newly_hidden(before, after):
    """The (cohort, race) rows hide_across_cohorts hid."""
    return {key for key, row in after.items() if row.suppressed and not before[key].suppressed}


def test_a_lone_hidden_single_year_row_is_covered_by_another_year():
    # Black is hidden in 2022-23 only: the pool minus 2023-24 would give it, so 2023-24's Black is hidden too.
    # Both years already hide two other races, so their own lines need nothing more.
    sizes = {C2022: [50, 5, 4, 3], C2023: [50, 40, 3, 2]}
    before, after = pooled_by_race(sizes)
    assert newly_hidden(before, after) == {(C2023, "Black or African American")}
    assert after[(C2023, "Black or African American")].note == "note." + ACROSS_NOTE
    assert {key: row for key, row in after.items() if key[0] == POOL} == {key: row for key, row in before.items() if key[0] == POOL}


def test_a_hidden_pooled_row_is_covered_by_its_smallest_year():
    # The pool's Black row is hidden (as cover in the pool's own line), but adding up both years would give it.
    sizes = {C2022: [100, 20, 4, 3], C2023: [100, 25, 3, 2]}
    before, after = pooled_by_race(sizes, covers=[(POOL, "Black or African American")])
    assert newly_hidden(before, after) == {(C2022, "Black or African American")}
    assert after[(POOL, "Black or African American")] == before[(POOL, "Black or African American")]


def test_a_cover_in_one_year_is_checked_again_in_that_years_own_line():
    # 2022-23 hides Black and Hispanic, 2023-24 hides nothing. Covering one of them in 2023-24 leaves it alone in
    # 2023-24's race line, so a second 2023-24 race is hidden there. The other one is picked, because its pool
    # line already hides 2022-23's row: Asian or White would leave a new line with one hidden row.
    sizes = {C2022: [50, 5, 4, 60], C2023: [50, 40, 30, 60]}
    before, after = pooled_by_race(sizes)
    covered = {(C2023, "Black or African American"), (C2023, "Hispanic")}
    assert newly_hidden(before, after) == covered
    assert sorted(after[key].note for key in covered) == sorted(["note." + ACROSS_NOTE, "note." + COMPLEMENT_NOTE])
    assert not any(row.suppressed for key, row in after.items() if key[0] == POOL)


def test_a_pool_without_every_one_of_its_years_has_no_line():
    # Without 2023-24 in the run, the pool and 2022-23 alone don't add up to anything.
    sizes = {C2022: [50, 5, 4, 3], C2023: [50, 40, 3, 2]}
    before, after = pooled_by_race(sizes, years=(C2022,))
    assert after == before


def test_a_hidden_year_row_nobody_is_counted_in_needs_no_cover():
    # 2022-23's Black students are all out of scope: the pool minus 2023-24 gives 0 / 0, which is no secret.
    sizes = {C2022: [50, OUT_OF_SCOPE_ONLY, 4, 3], C2023: [50, 40, 3, 2]}
    before, after = pooled_by_race(sizes)
    assert newly_hidden(before, after) == set()


def test_a_cover_the_pool_gives_away_is_known_in_its_years_own_line():
    # 2022-23 hides Black (5) and, as cover, Hispanic (12). No 2023-24 Hispanic is counted, so the pool's Hispanic
    # row is 2022-23's exactly, and 2022-23's race line is left with Black alone: another 2022-23 race is hidden.
    sizes = {C2022: [50, 5, 12, 60], C2023: [50, 40, OUT_OF_SCOPE_ONLY, 60]}
    _, after, all_counts = pooled_run(sizes)
    assert worked_out(after, all_counts) == []
    hidden_2022 = {next(iter(r.group.parts)).value for r in after if r.cohort == C2022 and r.group.parts and r.suppressed}
    assert len(hidden_2022 - {"Black or African American", "Hispanic"}) >= 1


def test_a_cover_known_from_the_pool_needs_cover_of_its_own():
    # 2023-24's White (12) covers it for 2022-23's White (5), and 2023-24's Asian (20) covers for that. No 2022-23
    # Asian is counted, so the pool's Asian row gives 2023-24's away, and with it the White and 2022-23's 5. Treating
    # the Asian as known hides one more 2023-24 race, then its pool line's 2022-23 row.
    sizes = {C2022: [OUT_OF_SCOPE_ONLY, 20, 15, 5], C2023: [20, 60, 0, 12]}
    before, after, all_counts = pooled_run(sizes)
    assert worked_out(after, all_counts) == []
    assert [r for r in after if r.cohort == POOL] == [r for r in before if r.cohort == POOL]


@pytest.mark.parametrize("measure", list(MEASURES))
@pytest.mark.parametrize("dimension", [GroupDimension.RACE, GroupDimension.PELL, GroupDimension.COHORT_TERM])
def test_single_years_never_change_the_pooled_rows(database, measure, dimension):
    # The pool reads the same run alone or with its years, and no pool line has exactly one hidden row.
    group_by = [GroupBy.of(dimension)]
    alone = run_measure(measure, [POOL], group_by, database=database)
    together = run_measure(measure, [POOL, C2022, C2023], group_by, database=database)
    assert [r for r in together if r.cohort == POOL] == alone

    groups = groups_for(group_by, read_open_values(database, MEASURES[measure], [POOL, C2022, C2023], group_by))
    counts = MEASURES[measure].count(database, [POOL, C2022, C2023], groups)
    rows = {(r.cohort, r.group): r for r in together}
    # A pool with no answers yet publishes no numbers, so its years have nothing to be subtracted from.
    if rows[(POOL, EVERYONE)].status == Status.NOT_YET_OBSERVABLE:
        pytest.skip("the pool has no answers yet, so it publishes no numbers to subtract from")
    for group in groups[1:]:
        line = [(cohort, group) for cohort in (POOL, C2022, C2023)]
        hidden = [key for key in line if rows[key].suppressed and counts[key].denominator > 0]
        shown = [key for key in line[1:] if not rows[key].suppressed]
        assert len(hidden) != 1 or not shown, group.label


# A deeper total run beside its breakdown, such as course x race beside course x gender x race (manifest version 6).
COURSE_RACE = GroupBy.of(GroupDimension.COURSE, GroupDimension.RACE)
COURSE_GENDER = GroupBy.of(GroupDimension.COURSE, GroupDimension.GENDER)
RACE_GENDER = GroupBy.of(GroupDimension.RACE, GroupDimension.GENDER)
BY_COURSE = GroupBy.of(GroupDimension.COURSE)
BLACK = "Black or African American"


def by_course(sizes, totals):
    """DFW rows for course x gender x race and the total breakdowns given, after hide_complements, with the counts.

    sizes maps (course, gender, race) to a size, students or Counts. A total's counts add up its groups' counts.
    """
    pieces = defaultdict(list)  # each group's three-way counts, to add up
    for (course, gender, race), size in sizes.items():
        values = {GroupDimension.COURSE: course, GroupDimension.GENDER: gender, GroupDimension.RACE: race}
        pieces[EVERYONE].append(as_counts(size))
        for total in totals:
            pieces[Group.of(*((d, values[d]) for d in total.dimensions))].append(as_counts(size))
        pieces[Group.of(*values.items())].append(as_counts(size))
    all_counts = {(C2022, group): summed(counts) for group, counts in pieces.items()}
    results = [build_result(Measure.DFW_RATE, C2022, group, all_counts[(C2022, group)], "note.") for group in pieces]
    return hide_complements(results, all_counts), all_counts


def covers(results):
    """The labels of the groups hidden only as cover."""
    return {r.group.label for r in results if r.note.endswith(COMPLEMENT_NOTE)}


def test_a_course_x_race_total_in_the_run_is_hidden_first_as_cover():
    # ENGL 1302's Asian men (5) are alone in their gender line, which adds up to ENGL 1302 x Asian (45). Hiding
    # that total covers them, so the 40 Asian women stay shown. The total's own lines are then checked like any
    # hidden row's: Asian across courses is left with it alone, so MATH 1314 x Asian (70) is hidden too, and its
    # gender line, now with only its total hidden, hides its smallest group, the 30 Asian men.
    sizes = {}
    for course, asian_men in (("ENGL 1302", 5), ("MATH 1314", 30)):
        sizes.update({
            (course, "M", "Asian"): asian_men, (course, "F", "Asian"): 40, (course, "M", "White"): 50,
            (course, "F", "White"): 60, (course, "M", "Hispanic"): 2, (course, "F", "Hispanic"): 3,
        })
    results, all_counts = by_course(sizes, [COURSE_RACE])
    assert covers(results) == {"course=ENGL 1302, race=Asian", "course=MATH 1314, race=Asian",
                               "course=MATH 1314, gender=M, race=Asian"}
    assert find(results, "course=ENGL 1302, gender=F, race=Asian").status == Status.OK
    assert recoverable(results, all_counts) == []


def test_the_total_covers_a_line_whose_other_group_equals_a_shown_total():
    # MAN 2150's only women counted are White (30), so they equal the MAN 2150 women's row of course x gender.
    # The 8 White men are alone in their gender line: hiding the White women would cover nothing, since course
    # x race White minus that course x gender row gives the 8 back. Hiding the course x race total covers them.
    sizes = {
        ("MAN 2150", "M", "White"): 8, ("MAN 2150", "F", "White"): 30, ("MAN 2150", "M", BLACK): 20,
        ("MAN 2150", "F", BLACK): OUT_OF_SCOPE_ONLY,
        ("ENGL 1302", "M", "White"): 50, ("ENGL 1302", "F", "White"): 60, ("ENGL 1302", "M", BLACK): 40,
        ("ENGL 1302", "F", BLACK): 45,
    }
    results, all_counts = by_course(sizes, [COURSE_RACE, COURSE_GENDER])
    assert "course=MAN 2150, race=White" in covers(results)
    assert recoverable(results, all_counts) == []


def test_a_deeper_total_hidden_as_cover_is_protected_by_its_own_line():
    # Hispanic men (7) and women (8) are hidden in race x gender, so Asian men and women are hidden as cover.
    # Asian women's courses (40, 40, 30) add up to that hidden total, so one of them is hidden too: otherwise
    # their sum gives the total back, and with it the Hispanic groups.
    sizes = {}
    for course, asian_men, asian_women, hispanic in (("ENGL 1302", 5, 40, (2, 3)), ("MATH 1314", 4, 40, (3, 2)),
                                                     ("STAT 1342", 30, 30, (2, 3))):
        sizes.update({
            (course, "M", "Asian"): asian_men, (course, "F", "Asian"): asian_women, (course, "M", "White"): 50,
            (course, "F", "White"): 60, (course, "M", "Hispanic"): hispanic[0], (course, "F", "Hispanic"): hispanic[1],
        })
    results, all_counts = by_course(sizes, [RACE_GENDER, BY_COURSE])
    assert covers(results) == {"gender=M, race=Asian", "gender=F, race=Asian", "course=STAT 1342, gender=F, race=Asian"}
    assert recoverable(results, all_counts) == []


def test_without_course_totals_a_course_is_the_sum_of_its_groups():
    # Version 5's course breakdowns: course x gender x race beside race x gender and course, but no course x race
    # or course x gender. ENGL 1302's 5 Asian men are its only hidden group, so its course row minus its other
    # groups would give them back: all its groups are one line, and the smallest other, 40 Asian women, is hidden
    # too. The same in MATH 1314. Asian men's line across courses hides two groups, so its total stays shown.
    sizes = {}
    for course, asian_men, asian_women in (("ENGL 1302", 5, 40), ("MATH 1314", 4, 40), ("STAT 1342", 30, 30)):
        sizes.update({
            (course, "M", "Asian"): asian_men, (course, "F", "Asian"): asian_women, (course, "M", "White"): 50,
            (course, "F", "White"): 60,
        })
    results, all_counts = by_course(sizes, [RACE_GENDER, BY_COURSE])
    assert covers(results) == {"course=ENGL 1302, gender=F, race=Asian", "course=MATH 1314, gender=F, race=Asian"}
    assert find(results, "gender=M, race=Asian").status == Status.OK
    assert recoverable(results, all_counts) == []


@pytest.mark.parametrize("measure", [Measure.DFW_RATE, Measure.MIDTERM_ALERT_RATE])
def test_race_by_gender_hides_the_same_beside_the_course_breakdowns(database, measure):
    # A race x gender row is the total of its line across courses, but not hidden first there: pages read it on
    # its own. So beside version 5's course breakdowns it is hidden just as when it is run alone.
    race_gender = GroupBy.of(GroupDimension.RACE, GroupDimension.GENDER)
    courses = [GroupBy.of(GroupDimension.COURSE), GroupBy.of(GroupDimension.COURSE, GroupDimension.RACE, GroupDimension.GENDER)]
    alone = run_measure(measure, [C2022], [race_gender], database=database)
    beside = {r.group: r for r in run_measure(measure, [C2022], [race_gender, *courses], database=database)}
    assert [beside[r.group] for r in alone] == alone


def test_a_rectangle_of_course_rows_is_a_line_too():
    # BIO 130 (32) minus its White (21) and women's (22) rows plus its White women (12) leaves the 1 Asian man,
    # its only one in neither. No single line gives him away, but that sum does, so it is a line too, and its
    # course x race and course x gender rows are hidden first.
    sizes = {
        ("BIO 130", "F", "White"): 12, ("BIO 130", "F", "Asian"): 3, ("BIO 130", "F", BLACK): 4,
        ("BIO 130", "F", "Hispanic"): 3, ("BIO 130", "M", "White"): 4, ("BIO 130", "M", "Asian"): 1,
        ("BIO 130", "UNKNOWN", "White"): 5,
    }
    for course, size in (("ENGL 1302", 40), ("MATH 1314", 50)):
        for gender in ("M", "F", "UNKNOWN"):
            for race in ("White", "Asian", BLACK, "Hispanic"):
                sizes[(course, gender, race)] = size + (7 if gender == "F" else 0) + len(race)
    results, all_counts = by_course(sizes, [RACE_GENDER, BY_COURSE, COURSE_RACE, COURSE_GENDER])
    assert {"course=BIO 130, race=White", "course=BIO 130, gender=F"} <= covers(results)
    assert find(results, "course=BIO 130").status == Status.OK
    assert recoverable(results, all_counts) == []


@pytest.mark.parametrize("tiny", [
    {("M", "White"): 8, ("F", "White"): 25},  # one race: its White row is the course row
    {("F", "White"): 8, ("F", BLACK): 25},  # one gender: its women's row is the course row
])
def test_a_cover_equal_to_a_course_row_is_avoided_before_the_first_covers(tiny):
    # TINY 101's course x race White (or course x gender F) row equals its course row, which is shown, so hiding it
    # would cover nothing. Being the only group counted in another line is checked before a line's first covers.
    sizes = {("TINY 101", gender, race): size for (gender, race), size in tiny.items()}
    for course, men, women in (("ENGL 1302", (50, 40, 30), (60, 45, 35)), ("MATH 1314", (52, 41, 31), (61, 44, 36))):
        for race, man, woman in zip(("White", BLACK, "Asian"), men, women):
            sizes.update({(course, "M", race): man, (course, "F", race): woman})
    results, all_counts = by_course(sizes, [RACE_GENDER, BY_COURSE, COURSE_RACE, COURSE_GENDER])
    assert weak_covers(results, all_counts) == []
    assert recoverable(results, all_counts) == []


def test_totals_outside_the_run_are_known_only_when_taken_as_published():
    # Gender X counts one student, of Two or More Races, and the run has no one-way gender row. Strict takes the
    # gender X total as published, so that row equals it and comes back. With totals_published False it doesn't:
    # the manifest runs each measure and cohort once, so a total outside the run is published nowhere.
    two = "Two or More Races"
    sizes = {("M", "Asian"): 50, ("M", "White"): 60, ("M", two): 20, ("F", "Asian"): 55, ("F", "White"): 65,
             ("F", two): 25, ("X", two): 1}
    groups = [Group.of((GroupDimension.GENDER, g), (GroupDimension.RACE, r)) for g, r in sizes]
    all_counts = {(C2022, g): as_counts(size) for g, size in zip(groups, sizes.values())}
    all_counts[(C2022, EVERYONE)] = summed(list(all_counts.values()))
    results = gender_by_race(sizes)
    assert recoverable(results, all_counts) == [("2022-23", "gender=X, race=Two or More Races")]
    assert recoverable(results, all_counts, totals_published=False) == []
    # Sums among the run's own rows still count: the pool's Black (35) minus 2023-24's (30) gives 2022-23's 5
    # until hide_across_cohorts covers it.
    before, after, all_counts = pooled_run({C2022: [50, 5, 40, 60], C2023: [50, 30, 40, 60]})
    assert recoverable(before, all_counts, totals_published=False) == [("2022-23", "race=Black or African American")]
    assert recoverable(after, all_counts, totals_published=False) == []


def test_fall_to_spring_retention_counts_fall_starters_with_a_first_fall_row(database):
    row = find(run_measure(Measure.FALL_TO_SPRING_RETENTION, [C2022], database=database), "everyone")
    # 1-12 have a fall 2022 row: 8 still enrolled, 2 not returning, 2 blank. Fall starters 13-14 have no fall row
    # and 15-24 started in spring, so all 12 are outside the measure.
    assert (row.numerator, row.denominator, row.metric_rate) == (8, 10, 0.8)
    assert row.exclusions == {ExclusionReason.UNKNOWN_OUTCOME: 2}
    assert row.n_out_of_scope == 12


def test_first_fall_good_standing_leaves_out_a_blank_standing(database):
    row = find(run_measure(Measure.FIRST_FALL_GOOD_STANDING, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (7, 10, 0.7)
    assert (row.n_excluded, row.exclusion_reason) == (2, ExclusionReason.NO_GRADED_CREDITS)
    assert row.n_out_of_scope == 12


def test_first_fall_measures_read_only_the_cohort_years_fall(database):
    # Student 1's fall 2023 row says not returning and not in good standing. It isn't their first fall, so
    # 2023-24 reads only 25-36, and pooling adds the two years without counting student 1 twice.
    pooled = Cohort.of("2022-23", "2023-24")
    retention = find(run_measure(Measure.FALL_TO_SPRING_RETENTION, [pooled], database=database), "everyone")
    standing = find(run_measure(Measure.FIRST_FALL_GOOD_STANDING, [pooled], database=database), "everyone")
    assert (retention.numerator, retention.denominator) == (18, 22)
    assert (standing.numerator, standing.denominator) == (19, 22)


def test_first_fall_measures_are_not_yet_observable_with_blank_answers(database):
    for measure in (Measure.FALL_TO_SPRING_RETENTION, Measure.FIRST_FALL_GOOD_STANDING):
        row = find(run_measure(measure, [Cohort.of("2024-25")], database=database), "everyone")
        assert row.status == Status.NOT_YET_OBSERVABLE


def test_first_fall_measures_by_cohort_term(database):
    # Only fall starters can be in scope, so the spring group has nobody counted.
    counts = counted(database, Measure.FALL_TO_SPRING_RETENTION, GroupDimension.COHORT_TERM)
    assert counts["cohort_term=Fall"] == (8, 10)
    assert counts["cohort_term=Spring"] == (0, 0)


def test_midterm_alert_rate(database):
    row = find(run_measure(Measure.MIDTERM_ALERT_RATE, [C2022], database=database), "everyone")
    assert (row.numerator, row.denominator, row.metric_rate) == (11, 22, 0.5)
    # 23 and the three MATH 1314 classes have no midterm grade. 21 withdrew before midterm.
    assert row.exclusions == {ExclusionReason.NO_MIDTERM_GRADE: 4}
    assert row.n_out_of_scope == 1


def test_midterm_alert_rate_by_course(database):
    counts = counted(database, Measure.MIDTERM_ALERT_RATE, GroupDimension.COURSE)
    assert counts == {"everyone": (11, 22), "course=ENGL 1302": (11, 22), "course=MATH 1314": (0, 0)}
    # Nobody in MATH 1314 is counted (no midterm grades), so there is nothing to protect and ENGL 1302 is shown.
    results = run_measure(Measure.MIDTERM_ALERT_RATE, [C2022], [GroupBy.of(GroupDimension.COURSE)], database=database)
    row = find(results, "course=ENGL 1302")
    assert (row.status, row.numerator, row.denominator) == (Status.OK, 11, 22)


def test_midterm_alert_leaves_out_an_unlisted_midterm_grade(database):
    add_student(database, "t1", "2025-26")
    for course, midterm in ((1, "d"), (2, " b "), (3, "X")):
        database.execute(
            "INSERT INTO course_enrollment VALUES ('t1', '2025-26', ?, '4', 914, '02')", (course,)
        )
        database.execute("INSERT INTO midterm_grade VALUES ('t1', 914, ?, '02', ?)", (course, midterm))
    cohort = Cohort.of("2025-26")
    counts = count_in_sql(database, midterm_alert.ENROLLMENT_SQL, [cohort], [EVERYONE])[(cohort, EVERYONE)]
    # Midterm grades match ignoring case and spaces. X isn't a midterm grade.
    assert (counts.numerator, counts.denominator) == (1, 2)
    assert counts.exclusions == {ExclusionReason.UNLISTED_GRADE: 1}


def test_midterm_join_needs_the_same_section(database):
    # A midterm grade for another section of the same course is not this enrollment's.
    add_student(database, "t1", "2025-26")
    database.execute("INSERT INTO course_enrollment VALUES ('t1', '2025-26', 1, 'F', 914, '02')")
    database.execute("INSERT INTO midterm_grade VALUES ('t1', 914, 1, '03', 'L')")
    cohort = Cohort.of("2025-26")
    counts = count_in_sql(database, midterm_alert.ENROLLMENT_SQL, [cohort], [EVERYONE])[(cohort, EVERYONE)]
    assert (counts.denominator, counts.exclusions) == (0, {ExclusionReason.NO_MIDTERM_GRADE: 1})


def test_midterm_recovery_rate(database):
    row = find(run_measure(Measure.MIDTERM_RECOVERY_RATE, [C2022], database=database), "everyone")
    # 11 alerts. 22's final grade is incomplete. 12, 13, 14 and 24 didn't end in a D, F or withdrawal.
    assert (row.numerator, row.denominator, row.metric_rate) == (4, 10, 0.4)
    assert row.exclusions == {ExclusionReason.INCOMPLETE: 1}
    assert row.n_out_of_scope == 0


def test_a_cohort_with_no_midterm_grades(database):
    cohort = Cohort.of("2023-24")
    alert = find(run_measure(Measure.MIDTERM_ALERT_RATE, [cohort], database=database), "everyone")
    assert alert.status == Status.NOT_YET_OBSERVABLE
    # Recovery only reads alerted enrollments, and there are none, so the row is hidden for size.
    recovery = find(run_measure(Measure.MIDTERM_RECOVERY_RATE, [cohort], database=database), "everyone")
    assert recovery.status == Status.SUPPRESSED


def test_midterm_notes_say_the_link_is_planted():
    for note in (midterm_alert.NOTE, midterm_recovery.NOTE):
        assert "PLANTED" in note and "circular" in note


def test_affinity_groups(database):
    counts = counted(database, Measure.RETENTION, GroupDimension.AFFINITY)
    # Student 1's second affinity row doesn't count them twice. "Student Government" matches ignoring spaces.
    assert counts["affinity=None"] == (12, 12)
    assert counts["affinity=Band"] == (4, 4)
    assert counts["affinity=Student Government"] == (0, 4)
    assert counts["affinity=UNKNOWN"] == (0, 0)


def test_educational_goal_comes_from_the_earliest_matrix_row(database):
    counts = counted(database, Measure.RETENTION, GroupDimension.EDUCATIONAL_GOAL)
    assert counts["educational_goal=graduate_and_transfer"] == (6, 6)
    assert counts["educational_goal=no_declaration"] == (6, 6)
    assert counts["educational_goal=graduate_and_find_job"] == (2, 2)
    # Student 1's later row doesn't change their goal. Students with no matrix row are UNKNOWN.
    assert counts["educational_goal=personal_enrichment"] == (0, 0)
    assert counts["educational_goal=UNKNOWN"] == (2, 6)


def test_enrichment_dimensions_work_with_the_enrollment_measures(database):
    counts = counted(database, Measure.MIDTERM_ALERT_RATE, GroupDimension.AFFINITY)
    # Every midterm grade from 12 on is an alert, except 21 (withdrew) and 23 (none).
    assert counts["affinity=None"] == (1, 12)
    assert counts["affinity=Band"] == (4, 4)
    assert counts["affinity=Student Government"] == (6, 6)


@pytest.mark.parametrize("measure", [Measure.DFW_RATE, Measure.CREDIT_COMPLETION])
def test_unmet_need_bands_add_up_to_everyone(database, measure):
    # The aid join is one row per student and year, so DFW's enrollments aren't repeated. A student with
    # no aid row (21 to 24 in 2022-23) is UNKNOWN, so the bands still add up to everyone.
    counts = counted(database, measure, GroupDimension.UNMET_NEED_BAND)
    everyone = counts.pop("everyone")
    assert set(counts) == {f"unmet_need_band={band}" for band in ("$0", "$1-2k", "$2-5k", "$5k+", "UNKNOWN")}
    assert sum(numerator for numerator, _ in counts.values()) == pytest.approx(everyone[0])
    assert sum(denominator for _, denominator in counts.values()) == everyone[1]
    assert counts["unmet_need_band=UNKNOWN"][1] == 2


def test_rows_grouped_by_affinity_or_goal_say_they_are_noise(database):
    group_by = [GroupBy.of(GroupDimension.PELL), GroupBy.of(GroupDimension.AFFINITY), GroupBy.of(GroupDimension.EDUCATIONAL_GOAL)]
    results = run_measure(Measure.RETENTION, [C2022], group_by, database=database)
    for row in results:
        dimensions = {part.dimension for part in row.group.parts}
        noisy = bool(dimensions & {GroupDimension.AFFINITY, GroupDimension.EDUCATIONAL_GOAL})
        # Shown, hidden and cover rows all carry it; everyone and pell rows don't.
        assert row.note.endswith(NOISE_NOTE) == noisy, row.group.label
    assert find(results, "affinity=Band").suppressed

