"""Runs a measure and returns its result rows.

Each measure's calculation lives in its own file in calculations/ and counts in SQL or in Python. This file
builds the groups, asks the measure for its counts, hides small groups, works out the rate and checks the rows.

The equity gap finder calls run_measure, so keep its inputs and rows stable.
"""
from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import replace
from itertools import product
from pathlib import Path

from .calculations import (
    completion,
    credit_completion,
    dfw,
    fall_to_spring_retention,
    first_fall_good_standing,
    gateway_english,
    gateway_math,
    midterm_alert,
    midterm_recovery,
    part_time_share,
    persistence,
    retention,
    transfer_in_share,
)
from .models import (
    ALLOWED_VALUES,
    OPEN_DIMENSIONS,
    EVERYONE,
    SUPPRESSION_THRESHOLD,
    Cohort,
    Counts,
    Group,
    GroupBy,
    GroupDimension,
    Measure,
    MeasureResult,
    Status,
    check_unique,
)
from .save_results import RESULTS_DATABASE, save_results

logger = logging.getLogger(__name__)

# Where the loader writes its SQLite database.
DEFAULT_DATABASE = Path(__file__).parent.parent / "normalized-data-model" / "output" / "pdp.sqlite"

# Add a measure by writing its file in calculations/ and listing it here.
MEASURES = {
    Measure.RETENTION: retention,
    Measure.PERSISTENCE: persistence,
    Measure.GATEWAY_MATH: gateway_math,
    Measure.GATEWAY_ENGLISH: gateway_english,
    Measure.DFW_RATE: dfw,
    Measure.CREDIT_COMPLETION: credit_completion,
    Measure.FALL_TO_SPRING_RETENTION: fall_to_spring_retention,
    Measure.FIRST_FALL_GOOD_STANDING: first_fall_good_standing,
    Measure.MIDTERM_ALERT_RATE: midterm_alert,
    Measure.MIDTERM_RECOVERY_RATE: midterm_recovery,
    Measure.COMPLETION: completion,
    Measure.TRANSFER_IN_SHARE: transfer_in_share,
    Measure.PART_TIME_SHARE: part_time_share,
}


def run_measure(
    measure: Measure,
    cohorts: list[Cohort],
    group_by: list[GroupBy] | None = None,
    database: str | Path | None = None,
    save: bool = False,
) -> list[MeasureResult]:
    """Return one row per cohort and group: everyone, plus every group asked for in group_by.

    database is the loaded SQLite file to read, or an open connection (for PostgreSQL). It defaults to
    the loader's file. save=True also writes the rows to the results database (see save_results.py).
    """
    if measure not in MEASURES:
        raise NotImplementedError(f"{measure.value} is not written yet")
    if not cohorts:
        raise ValueError("cohorts needs at least one Cohort")
    calculation = MEASURES[measure]
    check_open_dimensions(measure, calculation, group_by or [])

    connection, opened_here = open_database(database)
    try:
        groups = groups_for(group_by or [], read_open_values(connection, calculation, cohorts, group_by or []))
        all_counts = calculation.count(connection, cohorts, groups)
        sources = read_sources(connection)
    finally:
        if opened_here:
            connection.close()

    results = []
    for cohort in cohorts:
        for group in groups:
            results.append(build_result(measure, cohort, group, all_counts[(cohort, group)], calculation.NOTE))
    results = hide_complements(results, all_counts)
    results = hide_across_cohorts(results, all_counts)
    results = [with_noise_note(r) for r in results]
    check_unique(results)
    loaded_at = latest_load(sources)
    log_run(measure, cohorts, group_by or [], results, sources, describe_database(database))
    if save:
        save_results(results, loaded_at)
        logger.info("%s: saved %d rows to %s", measure.value, len(results), RESULTS_DATABASE)
    return results


def open_database(database: str | Path | None):
    """Return (connection, whether we opened it) for a SQLite file path, a connection, or the default file."""
    if database is not None and not isinstance(database, (str, Path)):
        return database, False
    path = Path(database) if database is not None else DEFAULT_DATABASE
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the loader first (see the README).")
    return sqlite3.connect(path), True


def read_sources(connection) -> list[tuple]:
    """Which files the loaded data came from: source file, SHA-256 and load time."""
    cursor = connection.cursor()
    cursor.execute("SELECT source_file, file_sha256, loaded_at FROM data_provider ORDER BY provider_id")
    return cursor.fetchall()


def describe_database(database: str | Path | None) -> str:
    """Where the data came from, for the log."""
    if database is None:
        return DEFAULT_DATABASE.as_posix()
    if isinstance(database, (str, Path)):
        return Path(database).as_posix()
    return "an open connection"


def latest_load(sources: list[tuple]) -> str:
    """When the data was last loaded, as an ISO string, or 'unknown' if nothing says.

    SQLite holds loaded_at as the loader's ISO text; PostgreSQL holds a TIMESTAMP, which comes back as a
    datetime. Both end up as the same string, so the results file and its JSON record can hold it.
    """
    latest = max((source[2] for source in sources), default="unknown")
    return latest.isoformat() if hasattr(latest, "isoformat") else str(latest)


def log_run(measure: Measure, cohorts: list[Cohort], group_by: list[GroupBy], results: list[MeasureResult], sources: list[tuple], database: str) -> None:
    """Log one summary of the run, and warn about what a reader of the numbers should know."""
    hidden = [r for r in results if r.suppressed]
    loaded_at = latest_load(sources)
    cohort_names = ", ".join(c.label for c in cohorts)
    group_names = ", ".join(" x ".join(sorted(d.value for d in g.dimensions)) for g in group_by) or "none"
    logger.info(
        "%s: read %s. cohorts [%s], grouped by [%s]: %d rows, %d shown, %d hidden. Data loaded %s from %d files.",
        measure.value, database, cohort_names, group_names, len(results), len(results) - len(hidden), len(hidden), loaded_at, len(sources),
    )
    for source_file, sha256, _ in sources:
        logger.debug("%s: data file %s sha256 %s", measure.value, source_file, sha256)

    too_new = sorted({r.cohort.label for r in results if r.status == Status.NOT_YET_OBSERVABLE})
    for label in too_new:
        logger.warning("%s: cohort %s has no answers yet, so all its rows are hidden.", measure.value, label)
    if results and len(hidden) == len(results):
        logger.warning("%s: every row is hidden. Check the cohorts and that the data is loaded.", measure.value)


def check_open_dimensions(measure: Measure, calculation, group_by: list[GroupBy]) -> None:
    """Refuse a dimension whose values come from the data when the measure doesn't support it."""
    supported = getattr(calculation, "SUPPORTED_OPEN_DIMENSIONS", frozenset())
    for entry in group_by:
        for dimension in entry.dimensions:
            if dimension in OPEN_DIMENSIONS and dimension not in supported:
                raise ValueError(f"{measure.value} can't be grouped by {dimension.value}")


def read_open_values(connection, calculation, cohorts: list[Cohort], group_by: list[GroupBy]) -> dict[GroupDimension, list[str]]:
    """The values in the data for each open dimension asked for, such as every course taught in the cohorts."""
    wanted = {d for entry in group_by for d in entry.dimensions if d in OPEN_DIMENSIONS}
    return {dimension: calculation.open_values(connection, dimension, cohorts) for dimension in wanted}


def groups_for(group_by: list[GroupBy], open_values: dict[GroupDimension, list[str]] | None = None) -> list[Group]:
    """Everyone, plus every combination of values for each GroupBy. open_values has the values found in the data."""
    open_values = open_values or {}
    groups = [EVERYONE]
    for entry in group_by:
        dimensions = sorted(entry.dimensions, key=lambda d: d.value)
        value_choices = [open_values[d] if d in OPEN_DIMENSIONS else sorted(ALLOWED_VALUES[d]) for d in dimensions]
        for values in product(*value_choices):
            groups.append(Group.of(*zip(dimensions, values)))
    return groups


def build_result(measure: Measure, cohort: Cohort, group: Group, counts: Counts, note: str) -> MeasureResult:
    """Turn counts into a result row, hiding the group if its cohort isn't observable yet or it has too few students."""
    if counts.not_yet_observable:
        return hidden_result(measure, cohort, group, Status.NOT_YET_OBSERVABLE, note)
    if counts.n_students < SUPPRESSION_THRESHOLD:
        return hidden_result(measure, cohort, group, Status.SUPPRESSED, note)

    return MeasureResult(
        measure=measure,
        cohort=cohort,
        group=group,
        numerator=counts.numerator,
        denominator=counts.denominator,
        metric_rate=round(counts.numerator / counts.denominator, 4),
        status=Status.OK,
        n_excluded=counts.n_excluded,
        n_out_of_scope=counts.n_out_of_scope,
        exclusion_reason=counts.exclusion_reason,
        note=note,
        exclusions=dict(counts.exclusions),
    )


# Added to the note of every row grouped by a synthetic dimension that no outcome depends on.
NOISE_DIMENSIONS = frozenset({GroupDimension.AFFINITY, GroupDimension.EDUCATIONAL_GOAL})
NOISE_NOTE = (
    " Affinity and educational goal are synthetic and independent of every outcome (except educational_goal "
    "UNKNOWN, which is a scope artifact): any other difference is noise."
)


def with_noise_note(result: MeasureResult) -> MeasureResult:
    """The row with NOISE_NOTE added when its group uses a noise dimension, shown or hidden. Other rows are unchanged."""
    if not any(part.dimension in NOISE_DIMENSIONS for part in result.group.parts):
        return result
    return replace(result, note=result.note + NOISE_NOTE)


# Added to the note of a group hidden only to protect a smaller one.
COMPLEMENT_NOTE = " Also hidden so a smaller hidden group can't be worked out by subtraction."


def hide_complements(results: list[MeasureResult], all_counts: dict) -> list[MeasureResult]:
    """Hide more groups until no hidden group can be worked out by subtraction from a total.

    A line is a breakdown's groups with every dimension but one held fixed, and it adds up to a total: a one-way
    breakdown adds up to everyone, and each row and column of gender x race adds up to one gender or one race.
    While a line has exactly one hidden group that anyone is counted in, one more of its shown groups is hidden.
    Hiding a group can leave another line with one hidden group, so those lines are checked again. A hidden group
    nobody is counted in, such as an UNKNOWN group whose students are all out of scope, adds 0 to the line's
    numerator and denominator: it is no cover, and needs none. Which lines are checked: see lines_by_key.
    """
    rows = {(r.cohort, r.group): r for r in results}
    lines, lines_of = lines_by_key(rows)

    def is_hidden(cohort, group) -> bool:
        return rows[(cohort, group)].suppressed and is_counted(all_counts[(cohort, group)])

    def cost(cohort, group, line_key) -> tuple:
        # First avoid a group that is the only one counted in another line: it equals that line's published
        # total, so it covers nothing. (A line holding its own total counts that total, so no group is alone
        # there: one equal to it leaves that line with one hidden group, and the total is hidden next.) Then the
        # line's first covers (first_covers), then a group whose other lines already hide someone, then the smallest.
        others = [key for key in lines_of[(cohort, group)] if key != line_key]
        alone = any(all(g == group or not is_counted(all_counts[(cohort, g)]) for g in lines[key]) for key in others)
        not_first = group not in first_covers(line_key)
        opens = sum(1 for key in others if not any(is_hidden(cohort, g) for g in lines[key]))
        return alone, not_first, opens, all_counts[(cohort, group)].n_students, group.label

    pending = list(lines)
    while pending:
        key = pending.pop()
        cohort = key[0]
        hidden = [g for g in lines[key] if is_hidden(cohort, g)]
        shown = [g for g in lines[key] if not rows[(cohort, g)].suppressed]
        if len(hidden) != 1 or not shown:
            continue
        cover = min(shown, key=lambda g: cost(cohort, g, key))
        everyone = rows[(cohort, EVERYONE)]
        rows[(cohort, cover)] = hidden_result(everyone.measure, cohort, cover, Status.SUPPRESSED, everyone.note + COMPLEMENT_NOTE)
        pending.extend(lines_of[(cohort, cover)])
    return [rows[(r.cohort, r.group)] for r in results]


# Added to the note of a single-cohort group hidden only to protect a group in a pooled cohort's line.
ACROSS_NOTE = " Also hidden so a smaller group can't be worked out from the pooled cohorts."


def hide_across_cohorts(results: list[MeasureResult], all_counts: dict) -> list[MeasureResult]:
    """Hide more single-cohort groups until no hidden group can be worked out from a pooled cohort and its years.

    A pooled cohort's group adds up to the same group in each of its years, so when a run holds a pool and every
    one of its years, those rows are one more line. While such a line has exactly one hidden group that anyone is
    counted in (the pool's row included), one of its shown single-year rows is hidden too, picked as hide_complements
    picks, so usually the smallest. A pooled row is never hidden here, so the pool reads the same with or without
    its years. Hiding a single-year row can leave one of that year's own lines (lines_by_key) with one hidden group,
    so those are checked again, as hide_complements does.

    A line with one hidden group and no shown single-year row left to hide gives that group away: the pool's row
    minus the other years, say, is a cover's exact count. Such a group is then treated as known, as if shown, and
    its other lines are checked again, so it can't be used to work out a smaller group beside it. Everyone rows
    aren't in these lines: hiding a year's everyone row would leave its groups no total.
    """
    rows = {(r.cohort, r.group): r for r in results}
    cohorts = {r.cohort for r in results}
    # A pool with no answers yet publishes no numbers at all, so there is nothing to subtract its years from.
    pools = [
        c for c in cohorts
        if len(c.years) > 1 and all(Cohort.of(year) in cohorts for year in c.years)
        and rows[(c, EVERYONE)].status != Status.NOT_YET_OBSERVABLE
    ]
    if not pools:
        return results
    singles = {Cohort.of(year) for pool in pools for year in pool.years}
    notes = {cohort: rows[(cohort, EVERYONE)].note for cohort in singles}

    # Each line is a list of (cohort, group) rows: the pools' and years' own lines, then each pool's line per group.
    # A pool's own lines have nothing to hide, but a group known from one can give away another.
    lines, lines_of = defaultdict(list), defaultdict(list)
    own_lines, _ = lines_by_key({key: row for key, row in rows.items() if key[0] in singles or key[0] in pools})
    for key, groups in own_lines.items():
        for group in groups:
            lines[key].append((key[0], group))
            lines_of[(key[0], group)].append(key)
    for pool in sorted(pools, key=lambda c: c.label):
        for cohort, group in rows:
            if cohort != pool or group == EVERYONE:
                continue
            key = ("across", pool, group)
            for member in [(pool, group), *((Cohort.of(year), group) for year in sorted(pool.years))]:
                lines[key].append(member)
                lines_of[member].append(key)

    known = set()  # hidden rows whose counts some line gives away

    def is_unknown(member) -> bool:
        """Whether the row is hidden, counts someone, and no line gives its counts away."""
        return rows[member].suppressed and is_counted(all_counts[member]) and member not in known

    def cost(member, line_key) -> tuple:
        # The same preferences as hide_complements: not alone in another line, then opening the fewest new
        # lines with one hidden group, then the smallest.
        others = [key for key in lines_of[member] if key != line_key]
        alone = any(all(m == member or not is_counted(all_counts[m]) for m in lines[key]) for key in others)
        opens = sum(1 for key in others if not any(is_unknown(m) for m in lines[key]))
        cohort, group = member
        return alone, opens, all_counts[member].n_students, cohort.label, group.label

    pending = list(lines)
    while pending:
        key = pending.pop()
        hidden = [m for m in lines[key] if is_unknown(m)]
        if len(hidden) != 1:
            continue
        shown = [m for m in lines[key] if m[0] in singles and not rows[m].suppressed]
        if not shown:
            # Nothing here can cover it, so its counts are out: check its other lines with it as known.
            known.add(hidden[0])
            pending.extend(lines_of[hidden[0]])
            continue
        cover = min(shown, key=lambda m: cost(m, key))
        cohort, group = cover
        note = notes[cohort] + (ACROSS_NOTE if key[0] == "across" else COMPLEMENT_NOTE)
        rows[cover] = hidden_result(rows[cover].measure, cohort, group, Status.SUPPRESSED, note)
        pending.extend(lines_of[cover])
    return [rows[(r.cohort, r.group)] for r in results]


def lines_by_key(rows: dict) -> tuple[dict, dict]:
    """(groups in each line, lines each group is in). Cohorts whose everyone row is hidden have none.

    A line's key is (cohort, its groups' dimensions, the dimension it varies, the parts it holds fixed). A line
    whose total is everyone or a one-way group is always checked: those totals are published nearly everywhere.
    A line whose total has two or more dimensions, such as course x race inside course x race x gender, is
    checked only when that total is in the run, and the total is then one of its groups, shown or hidden. So
    publish such a total only together with its breakdown. Lines across two dimensions of a course are added
    too: see course_lines.
    """
    lines, lines_of = defaultdict(list), defaultdict(list)
    for cohort, group in rows:
        if group == EVERYONE or rows[(cohort, EVERYONE)].suppressed:
            continue
        dimensions = frozenset(part.dimension for part in group.parts)
        for part in group.parts:
            total = Group(group.parts - {part})
            if len(total.parts) >= 2 and (cohort, total) not in rows:
                continue
            key = (cohort, dimensions, part.dimension, total.parts)
            lines[key].append(group)
            lines_of[(cohort, group)].append(key)
    # A deeper total is in the run, hidden or not, so it is one of its line's groups. Everyone and one-way
    # totals are taken as published, so they stay out.
    for key in list(lines):
        total = line_total(key)
        if len(total.parts) >= 2:
            lines[key].append(total)
            lines_of[(key[0], total)].append(key)
    for key, groups in course_lines(rows).items():
        lines[key] = groups
        for group in groups:
            lines_of[(key[0], group)].append(key)
    return lines, lines_of


# Stands where a rectangle line's key (course_lines) has the dimension other lines vary.
RECTANGLE = "rectangle"


def course_lines(rows: dict) -> dict:
    """Lines across two dimensions of a course's course x a x b groups, by key. Each adds up to the course row.

    A rectangle, keyed (cohort, dimensions, RECTANGLE, a group's parts): the course minus its course x a and
    course x b rows plus that group leaves the course's groups in neither a nor b. No one-dimension line holds
    that sum, but a reader can work it out. With neither course x a nor course x b in the run, the course is
    simply the sum of all its course x a x b groups: one line, keyed (cohort, dimensions, {a, b}, the course).
    Both need the course row shown: a hidden course is no known total.
    """
    by_course = defaultdict(list)  # (cohort, course part, dimensions) -> that course's three-way groups
    for cohort, group in rows:
        dimensions = frozenset(part.dimension for part in group.parts)
        if len(dimensions) == 3 and GroupDimension.COURSE in dimensions:
            course = next(part for part in group.parts if part.dimension == GroupDimension.COURSE)
            by_course[(cohort, course, dimensions)].append(group)

    lines = {}
    for (cohort, course, dimensions), groups in by_course.items():
        course_row = rows.get((cohort, Group(frozenset({course}))))
        if course_row is None or course_row.suppressed:
            continue
        corners = {group: [Group(group.parts - {part}) for part in group.parts if part != course] for group in groups}
        if not any((cohort, corner) in rows for group in groups for corner in corners[group]):
            lines[(cohort, dimensions, dimensions - {GroupDimension.COURSE}, frozenset({course}))] = list(groups)
            continue
        for group in groups:
            if any((cohort, corner) not in rows for corner in corners[group]):
                continue
            others = group.parts - {course}
            neither = [other for other in groups if not (other.parts & others)]
            lines[(cohort, dimensions, RECTANGLE, group.parts)] = [*corners[group], group, *neither]
    return lines


def line_total(line_key: tuple) -> Group:
    """The group a line (a key from lines_by_key) adds up to: the parts it holds fixed, or a rectangle's course."""
    if line_key[2] == RECTANGLE:
        return Group(frozenset(part for part in line_key[3] if part.dimension == GroupDimension.COURSE))
    return Group(line_key[3])


def first_covers(line_key: tuple) -> frozenset[Group]:
    """The groups hide_complements hides first in a line, before the line's other groups.

    A deeper total that holds a course, such as course x race in its gender line: hiding it keeps that course's
    finer groups shown. A rectangle's course x a and course x b rows, for the same reason. A total across courses,
    such as race x gender, is read on its own pages, so it gets no such preference.
    """
    if line_key[2] == RECTANGLE:
        course = line_total(line_key).parts
        return frozenset(Group(course | {part}) for part in line_key[3] - course)
    total = line_total(line_key)
    holds_course = any(part.dimension == GroupDimension.COURSE for part in total.parts)
    return frozenset({total}) if len(total.parts) >= 2 and holds_course else frozenset()


def is_counted(counts: Counts) -> bool:
    """Whether anyone in the group is counted in the measure, so it adds to its line's numerator and denominator."""
    # Cover protects the numerator and denominator only; n_excluded and n_out_of_scope can't be (README, Rules).
    # A denominator of 0 means a numerator of 0 only because every calculation's achieved is nonzero only when
    # has_answer = 1 (true for all 13 today). A new measure must keep that.
    return counts.denominator > 0


def hidden_result(measure: Measure, cohort: Cohort, group: Group, status: Status, note: str) -> MeasureResult:
    """A row with no numbers: the group is too small, or its cohort isn't observable yet."""
    return MeasureResult(
        measure=measure,
        cohort=cohort,
        group=group,
        numerator=None,
        denominator=None,
        metric_rate=None,
        status=status,
        n_excluded=None,
        n_out_of_scope=None,
        exclusion_reason=None,
        note=note,
    )
