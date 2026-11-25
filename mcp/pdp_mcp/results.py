"""The structured query builder: answers a spec from the published results, never SQL a caller writes.

A spec names a measure, a cohort, a breakdown and optional filters. It's refused unless
measures/manifest.yaml approves the measure, the cohort and the breakdown, and the refusal names what
is approved instead. The answer is a slice of success_measures (and equity_gaps for the gaps), read
as published. measures/publish.py writes each measure and cohort in one run, and a measure's
single cohorts in the same run as its pool. One run hides one set of groups, so rows from
different runs can't be set against each other, and success_measures and equity_gaps hide the same
groups. Within the run, hiding has the limits listed under Rules in measures/README.md: display
protection, not a guarantee.

The deploy reads a trimmed copy (playground/deploy/trim_measures.py) with hidden course groups absent
rather than blank, so a course breakdown's row_count and its first 200 rows differ from the full file.
That reveals nothing: a hidden row carries no numbers.

Nothing is recomputed: the builder filters, sorts and ranks published rows, and never does arithmetic on
a numerator, denominator, rate or gap. n_excluded, n_out_of_scope and exclusions are left out because they can be
under 10. Each row's status and note pass through: the note says when an effect is planted in the
synthetic data.

With include trends, each row also carries its change from the previous single cohort, read from the
measure_trends table publish wrote with the same rules the tiles use (measures/compare.py). It is read as
published too: nothing is compared here.

The REST endpoint, the MCP server and the chatbot all call this one builder (see the plan in the
design doc). This module needs no database and imports nothing from measures/: it reads the manifest
and the results file directly, so it runs from mcp/ as the rest of pdp_mcp does.
"""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .config import REPO_ROOT

__all__ = ["MAX_DIMENSIONS", "MAX_ROWS", "MAX_VALUE_LENGTH", "QueryAnswer", "ResultRow", "ResultsReader", "Spec", "SpecRefused",
           "Trend", "file_sha256", "publication_path", "spec_sql"]

# Publishing runs the measures against the loaded data model, so a stale model stops it before it
# writes anything. Saying both steps here saves running the one that fails.
PUBLISH_HINT = (
    "load the data model and publish the results "
    "(cd normalized-data-model && python -m src.pipeline.run, then python -m measures.publish)"
)


MANIFEST = REPO_ROOT / "measures" / "manifest.yaml"
RESULTS = REPO_ROOT / "measures" / "output" / "success_measures.sqlite"
MAX_DIMENSIONS = 3
MAX_ROWS = 200
# A where value's longest allowed length. Published values are under 70 characters; the cap keeps a
# value inside SQLite's LIKE pattern limit, so a huge one is a spec error rather than a crash.
MAX_VALUE_LENGTH = 200
GROUP_JOIN = " x "   # how the published files join a group's dimensions and values
EVERYONE = "all"     # the published group_dimensions and group_values of the everyone row
GAP_COLUMNS = ("gap_pts", "ci_low", "ci_high", "q_value", "likely_noise", "students_affected", "rank_by_affected")

# The SQL the builder runs. spec_sql shows these same strings, so what staff rerun can't drift from it.
MEASURE_SQL = ("SELECT group_values, status, numerator, denominator, metric_rate, note\n"
               "FROM success_measures\n"
               "WHERE measure = ? AND cohort = ? AND group_dimensions = ?")
WHERE_SQL = "\n  AND group_values LIKE ? ESCAPE '\\'"
# A hidden row's denominator is blank, so it never passes.
MIN_DENOMINATOR_SQL = "\n  AND denominator >= ?"
MEASURE_ORDER_SQL = "\nORDER BY group_values"
GAPS_SQL = (f"SELECT group_values, status, {', '.join(GAP_COLUMNS)},\n"
            "  CASE WHEN status = 'ok' THEN RANK() OVER compared END,\n"
            "  CASE WHEN status = 'ok' THEN COUNT(*) OVER (PARTITION BY status = 'ok') END\n"
            "FROM equity_gaps\n"
            "WHERE measure = ? AND cohort = ? AND group_dimensions = ?\n"
            "WINDOW compared AS (PARTITION BY status = 'ok' ORDER BY students_affected)")
EVERYONE_SQL = ("SELECT status, numerator, denominator, metric_rate, note\n"
                "FROM success_measures\n"
                "WHERE measure = ? AND cohort = ? AND group_dimensions = ?")
# Each single cohort's change from the one before, as measures/publish.py wrote it (manifest version 7).
TRENDS_SQL = ("SELECT group_values, previous_cohort, relative_pct, direction, judgement, label\n"
              "FROM measure_trends\n"
              "WHERE kpi = ? AND cohort = ? AND group_dimensions = ?")
# The cohort make-up measures, whose everyone denominator is the entering students: their answers also
# carry the entering students' trend. measures/models.py, MAKE_UP_MEASURES, names the same two.
ENTERING_MEASURES = ("transfer_in_share", "part_time_share")
ENTERING_STUDENTS = "entering_students"
SQL_SOURCE = "-- Published results (python -m measures.publish): sqlite3 measures/output/success_measures.sqlite"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Spec(_Model):
    """What to read. Every field must be approved by the manifest; where filters within the breakdown."""

    measure: str = Field(description="A measure the manifest lists, such as gateway_math.")
    cohort: str = Field(description="An approved cohort grouping, such as '2021-22 + 2022-23 + 2023-24'.")
    group_by: list[str] = Field(min_length=1, max_length=MAX_DIMENSIONS,
                                description="An approved breakdown, such as ['gender', 'race']. Order doesn't matter.")
    where: dict[str, Annotated[str, Field(max_length=MAX_VALUE_LENGTH)]] = Field(default_factory=dict,
                                  description="Keep only groups with these values, e.g. {'gender': 'M'}. Keys must be in group_by.")
    include: list[Literal["rates", "gaps", "trends"]] = Field(
        default_factory=lambda: ["rates"],
        description=("rates always; gaps adds each group's gap against everyone else; trends adds each row's change "
                     "from the previous single cohort, worded as the page's tiles word it (trend_label)."))
    min_denominator: int | None = Field(default=None, ge=1, description=(
        "Keep only groups whose published denominator is at least this. Hidden groups, whose denominator "
        "is blank, always drop out when it's set."))


class ResultRow(_Model):
    """One group's published numbers. A hidden group has blank numbers, never 0."""

    group: dict[str, str]
    status: str
    numerator: float | None
    denominator: float | None
    metric_rate: float | None
    note: str
    gap_status: str | None = None
    gap_pts: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    q_value: float | None = None
    likely_noise: bool | None = None
    students_affected: float | None = None
    rank_by_affected: int | None = Field(default=None, description=(
        "The gap finder's rank among every group published for this measure and cohort, across all its "
        "breakdowns, by students affected (1 is the most behind). Not a rank within this breakdown alone."))
    rank_in_breakdown: int | None = Field(default=None, description=(
        "Rank among this breakdown's compared groups, 1 = most behind, by students affected. Ranked across "
        "the whole breakdown even when where narrows the rows; tied groups share a rank."))
    ranked_of: int | None = Field(default=None,
                                  description="How many of this breakdown's groups were compared and ranked.")
    trend_vs: str | None = Field(default=None, description=(
        "With include trends: the previous single cohort the rate is compared with. Blank for a pool, for a "
        "hidden row or one hidden the year before, and for a year the manifest gives no trend (no_trend)."))
    trend_pct: float | None = Field(default=None, description="The relative change in the rate, in percent, to one decimal.")
    trend_direction: str | None = Field(default=None, description="up, down or flat (a change under 1% is flat).")
    trend_judgement: str | None = Field(default=None, description="good, bad or neutral, by which way is better.")
    trend_label: str | None = Field(default=None, description=(
        "The change as the tile's arrow says it, e.g. '−3.5% vs 2022-23'. Quote it as given."))


class Trend(_Model):
    """One published change from the previous single cohort, for a count rather than a rate."""

    vs: str
    pct: float
    direction: str
    judgement: str
    label: str


class QueryAnswer(_Model):
    """The slice a spec asked for, the everyone row to compare it with, and where the numbers came from."""

    spec: Spec
    everyone: ResultRow
    rows: list[ResultRow]
    row_count: int
    truncated: bool
    max_rows: int | None = Field(description="The most rows an answer holds, or null when the caller read it uncapped.")
    entering_students_trend: Trend | None = Field(default=None, description=(
        "With include trends, for transfer_in_share and part_time_share: the change in entering students (the "
        "everyone row's denominator) from the previous single cohort. Blank otherwise."))
    data_loaded_at: str
    manifest_version: int
    source: Literal["synthetic"] = "synthetic"


class SpecRefused(ValueError):
    """The spec asks for something the manifest doesn't approve, or the results can't be trusted."""

    def __init__(self, message: str, approved: dict | None = None):
        super().__init__(message)
        self.approved = approved or {}


class ResultsReader:
    """Answers specs from one published results file, checked against the manifest it was published from."""

    def __init__(self, manifest_path: Path = MANIFEST, results_path: Path = RESULTS):
        self.manifest_path = manifest_path
        self.results_path = results_path
        self._checked: tuple | None = None   # (results size, mtime, manifest sha) last found to match

    def approved(self) -> dict:
        """Every approved measure with its cohorts and breakdowns, as a caller would write them in a spec.

        The pooled cohorts come first, then any single cohorts. A single cohort has only some of the
        breakdowns listed: a spec asking for another is refused with the ones it has."""
        manifest = self._manifest()
        pools = [cohort_label(years) for years in manifest["cohorts"]]
        singles = manifest["single_cohorts"]
        return {measure: {"cohorts": pools + (singles if measure in manifest["single_measures"] else []),
                          "group_by": [sorted(dims) for dims in breakdowns]}
                for measure, breakdowns in manifest["measures"].items()}

    def breakdowns(self, measure: str, cohort: str, manifest: dict | None = None) -> list[list[str]]:
        """The breakdowns a spec may name for this measure and cohort, each sorted; empty when neither is approved.

        A single cohort has only the breakdowns listed for it under single_cohorts. query() checks specs with
        this too, so a page asking it first can't disagree with the builder. manifest is one already read."""
        manifest = manifest or self._manifest()
        if measure not in manifest["measures"]:
            return []
        if cohort in manifest["single_cohorts"]:
            listed = manifest["single_measures"].get(measure, [])
        elif cohort in [cohort_label(years) for years in manifest["cohorts"]]:
            listed = manifest["measures"][measure]
        else:
            return []
        return [sorted(dims) for dims in listed]

    def query(self, spec: Spec, *, max_rows: int | None = MAX_ROWS) -> QueryAnswer:
        """The slice of the published results that spec asks for, or SpecRefused saying why not.

        max_rows=None reads every row. Only Python callers (the pages) pass it: it isn't in Spec, so the
        REST route, the MCP server and the chatbot keep the cap."""
        manifest = self._manifest()
        self._check_spec(spec, manifest)
        record = self.check_publication()
        dimensions = GROUP_JOIN.join(sorted(spec.group_by))
        # One row past the cap is enough to know the answer was cut.
        limit = None if max_rows is None else max_rows + 1
        with closing(self._connect()) as connection:
            found = self._measure_rows(connection, spec, dimensions, limit)
            gaps = self._gaps(connection, spec, dimensions) if "gaps" in spec.include else {}
            trending = "trends" in spec.include
            trends = self._trends(connection, spec.measure, spec.cohort, dimensions) if trending else {}
            rows = [self._row(dimensions, values, measure_row, {**gaps.get(values, {}), **trends.get(values, {})})
                    for values, measure_row in found]
            everyone_trend = self._trends(connection, spec.measure, spec.cohort, EVERYONE) if trending else {}
            everyone = self._row(EVERYONE, EVERYONE, self._everyone_row(connection, spec), everyone_trend.get(EVERYONE))
            entering = None
            if trending and spec.measure in ENTERING_MEASURES:
                found_entering = self._trends(connection, ENTERING_STUDENTS, spec.cohort, EVERYONE).get(EVERYONE)
                entering = None if found_entering is None else Trend(
                    **{key.removeprefix("trend_"): value for key, value in found_entering.items()})
            # With min_denominator, no rows can mean every match was too small, not a wrong value.
            unmatched = spec.where and not rows and not self._measure_rows(
                connection, spec.model_copy(update={"min_denominator": None}), dimensions, 1)
        if unmatched:
            raise SpecRefused(f"no {dimensions} group matches {spec.where}: check the values",
                              {"values": self._values(spec, dimensions)})
        shown = rows if max_rows is None else rows[:max_rows]
        return QueryAnswer(spec=spec, everyone=everyone, rows=shown, row_count=len(shown),
                           truncated=len(rows) > len(shown), max_rows=max_rows, entering_students_trend=entering,
                           data_loaded_at=record["data_loaded_at"], manifest_version=record["manifest_version"])

    def _manifest(self) -> dict:
        """The manifest as written: version, cohorts as year lists, measures to breakdown sets, and its checksum.

        single_cohorts and single_measures are the single years' labels and each measure's breakdown sets
        for them, both empty when the manifest publishes none."""
        raw = self.manifest_path.read_bytes()
        data = yaml.safe_load(raw) or {}
        singles = data.get("single_cohorts") or {}
        return {
            "version": data.get("version"),
            "cohorts": [[str(year) for year in years] for years in data.get("cohorts") or []],
            "measures": breakdown_sets(data.get("measures")),
            "single_cohorts": [str(year) for year in singles.get("years") or []],
            "single_measures": breakdown_sets(singles.get("measures")),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def _check_spec(self, spec: Spec, manifest: dict) -> None:
        """Refuse a spec the manifest doesn't approve, naming what it does approve."""
        approved = self.approved()
        if spec.measure not in manifest["measures"]:
            raise SpecRefused(f"{spec.measure!r} isn't an approved measure", {"measures": sorted(approved)})
        allowed = approved[spec.measure]
        if spec.cohort not in allowed["cohorts"]:
            raise SpecRefused(f"cohort {spec.cohort!r} isn't approved for {spec.measure}", {"cohorts": allowed["cohorts"]})
        if len(set(spec.group_by)) != len(spec.group_by):
            raise SpecRefused("group_by names a dimension twice", {"group_by": allowed["group_by"]})
        if frozenset(spec.group_by) not in manifest["measures"][spec.measure]:
            raise SpecRefused(f"{spec.measure} by {', '.join(sorted(spec.group_by))} isn't approved",
                              {"group_by": allowed["group_by"]})
        # The pool's list passed, so a refusal here is a breakdown the single cohort doesn't have.
        breakdowns = self.breakdowns(spec.measure, spec.cohort, manifest)
        if sorted(spec.group_by) not in breakdowns:
            raise SpecRefused(f"{spec.measure} by {', '.join(sorted(spec.group_by))} isn't approved for {spec.cohort}",
                              {"group_by": breakdowns})
        outside = sorted(set(spec.where) - set(spec.group_by))
        if outside:
            raise SpecRefused(f"where can only filter the breakdown's own dimensions, not {', '.join(outside)}",
                              {"group_by": allowed["group_by"]})

    def check_publication(self) -> dict:
        """The publication record, once the results file and the manifest are shown to be the ones it names."""
        manifest = self._manifest()
        if not self.results_path.exists():
            raise SpecRefused(f"{self.results_path} not found: {PUBLISH_HINT}")
        path = publication_path(self.results_path)
        if not path.exists():
            raise SpecRefused(f"{path.name} not found: {PUBLISH_HINT}")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("manifest_sha256") != manifest["sha256"]:
            raise SpecRefused("the results were published from a different manifest: publish them again")
        stat = self.results_path.stat()
        key = (stat.st_size, stat.st_mtime_ns, manifest["sha256"])
        if self._checked != key:
            # Hashing a large file takes a moment, so it's done once per file version, not per query.
            if record.get("results_sha256") != file_sha256(self.results_path):
                raise SpecRefused("the results file changed after it was published: publish it again")
            self._checked = key
        return record

    def _connect(self) -> sqlite3.Connection:
        """The results file, read-only."""
        return sqlite3.connect(f"file:{self.results_path}?mode=ro", uri=True)

    def _measure_rows(self, connection, spec: Spec, dimensions: str, limit: int | None) -> list[tuple]:
        """(group values, row) for the breakdown's groups that pass where and min_denominator, up to limit if set."""
        sql, params = measure_query(spec, dimensions)
        found = []
        for row in connection.execute(sql, params):
            # LIKE ignores case, so each row is checked for the exact values before it's kept.
            if matches(dimensions, row[0], spec.where):
                found.append((row[0], row[1:]))
                if limit is not None and len(found) >= limit:
                    break
        return found

    def _gaps(self, connection, spec: Spec, dimensions: str) -> dict[str, dict]:
        """Each of the breakdown's gap rows by group values, ranked within the whole breakdown.

        Ranked as the de-aggregation page ranks: compared (ok) rows only, by students affected, most
        negative (most behind) first. The rank and count cover every group, whatever where keeps."""
        gaps = {}
        for values, status, *numbers in connection.execute(GAPS_SQL, (spec.measure, spec.cohort, dimensions)):
            fields = dict(zip((*GAP_COLUMNS, "rank_in_breakdown", "ranked_of"), numbers))
            fields["likely_noise"] = None if fields["likely_noise"] is None else bool(fields["likely_noise"])
            gaps[values] = {"gap_status": status, **fields}
        return gaps

    def _trends(self, connection, kpi: str, cohort: str, dimensions: str) -> dict[str, dict]:
        """Each group's published trend fields by group values, for one KPI, cohort and breakdown.

        A pool has none, and neither has a group hidden in either year: publish wrote no row for them."""
        try:
            found = connection.execute(TRENDS_SQL, (kpi, cohort, dimensions)).fetchall()
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):
                raise SpecRefused(f"the results have no trends (published before manifest version 7): {PUBLISH_HINT}") from None
            raise
        return {values: {"trend_vs": previous, "trend_pct": pct, "trend_direction": direction,
                         "trend_judgement": judgement, "trend_label": label}
                for values, previous, pct, direction, judgement, label in found}

    def _everyone_row(self, connection, spec: Spec) -> tuple:
        """The everyone row for the measure and cohort."""
        found = connection.execute(EVERYONE_SQL, (spec.measure, spec.cohort, EVERYONE)).fetchone()
        if found is None:
            raise SpecRefused(f"the results have no {spec.measure} rows for {spec.cohort}: publish them again")
        return found

    def _row(self, dimensions: str, values: str, measure_row: tuple, extra: dict | None) -> ResultRow:
        """One published row, with the gap and trend fields the spec asked for, where publish saved them."""
        status, numerator, denominator, metric_rate, note = measure_row
        group = {} if dimensions == EVERYONE else dict(zip(dimensions.split(GROUP_JOIN), values.split(GROUP_JOIN)))
        return ResultRow(group=group, status=status, numerator=numerator, denominator=denominator,
                         metric_rate=metric_rate, note=note, **(extra or {}))

    def _values(self, spec: Spec, dimensions: str) -> dict[str, list[str]]:
        """Each dimension's published values in the breakdown, to help a caller fix a filter."""
        with closing(self._connect()) as connection:
            found = connection.execute(
                "SELECT DISTINCT group_values FROM success_measures WHERE measure = ? AND cohort = ? AND group_dimensions = ?",
                (spec.measure, spec.cohort, dimensions)).fetchall()
        names = dimensions.split(GROUP_JOIN)
        values = {name: set() for name in names}
        for (joined,) in found:
            for name, value in zip(names, joined.split(GROUP_JOIN)):
                values[name].add(value)
        return {name: sorted(seen)[:50] for name, seen in values.items()}


def measure_query(spec: Spec, dimensions: str) -> tuple[str, list]:
    """The success_measures SELECT and its parameters for the breakdown's groups that pass where and min_denominator."""
    sql = MEASURE_SQL
    params: list = [spec.measure, spec.cohort, dimensions]
    if spec.where:
        sql += WHERE_SQL
        params.append(like_pattern(dimensions, spec.where))
    if spec.min_denominator is not None:
        sql += MIN_DENOMINATOR_SQL
        params.append(spec.min_denominator)
    return sql + MEASURE_ORDER_SQL, params


def spec_sql(spec: Spec) -> str:
    """The SQL the builder runs for a spec, with its values written in, for staff to rerun on the results file.

    Built from the strings the builder executes. It shows the spec as given: checking it against the
    manifest is query()'s job, so call this only for a spec query() answered."""
    dimensions = GROUP_JOIN.join(sorted(spec.group_by))
    queries = [measure_query(spec, dimensions)]
    if "gaps" in spec.include:
        queries.append((GAPS_SQL, [spec.measure, spec.cohort, dimensions]))
    queries.append((EVERYONE_SQL, [spec.measure, spec.cohort, EVERYONE]))
    if "trends" in spec.include:
        queries.append((TRENDS_SQL, [spec.measure, spec.cohort, dimensions]))
        queries.append((TRENDS_SQL, [spec.measure, spec.cohort, EVERYONE]))
        if spec.measure in ENTERING_MEASURES:
            queries.append((TRENDS_SQL, [ENTERING_STUDENTS, spec.cohort, EVERYONE]))
    header = [SQL_SOURCE]
    if spec.where:
        header.append("-- The builder also keeps only exact matches of where (LIKE ignores case), "
                      f"and chat shows at most {MAX_ROWS} rows.")
    else:
        header.append(f"-- Chat shows at most {MAX_ROWS} rows.")
    statements = [_inline(sql, params) + ";" for sql, params in queries]
    return "\n".join(header) + "\n" + "\n\n".join(statements)


def _inline(sql: str, params: list) -> str:
    """sql with each ? replaced by its parameter as a SQL literal."""
    # Split first, so a ? inside a value isn't taken for a placeholder.
    pieces = sql.split("?")
    if len(pieces) != len(params) + 1:
        raise ValueError(f"{len(pieces) - 1} placeholders for {len(params)} parameters")
    parts = [pieces[0]]
    for param, piece in zip(params, pieces[1:]):
        parts.append(_literal(param) + piece)
    return "".join(parts)


def _literal(value) -> str:
    """A string or number as a SQL literal: strings single-quoted with quotes doubled."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise TypeError(f"no SQL literal for {value!r}")
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return str(value)


def matches(dimensions: str, values: str, where: dict[str, str]) -> bool:
    """Whether a published group has every value where asks for."""
    group = dict(zip(dimensions.split(GROUP_JOIN), values.split(GROUP_JOIN)))
    return all(group.get(key) == value for key, value in where.items())


def like_pattern(dimensions: str, where: dict[str, str]) -> str:
    """A LIKE pattern for group_values: each filtered dimension's value, any value (%) for the rest."""
    parts = []
    for name in dimensions.split(GROUP_JOIN):
        if name in where:
            # Values such as personal_enrichment hold LIKE's wildcards, so they're matched literally.
            value = where[name].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            parts.append(value)
        else:
            parts.append("%")
    return GROUP_JOIN.join(parts)


def breakdown_sets(entries) -> dict[str, list[frozenset]]:
    """Each measure's breakdowns as written in the manifest, as sets of dimensions."""
    return {name: [frozenset(dims) for dims in listed] for name, listed in (entries or {}).items()}


def cohort_label(years: list[str]) -> str:
    """A cohort as the measures label it, oldest first, e.g. '2021-22 + 2022-23'."""
    return " + ".join(sorted(years))


def publication_path(results: Path) -> Path:
    """The publication record beside a results file, as measures/publish.py names it."""
    return results.with_name(f"{results.stem}.publication.json")


def file_sha256(path: Path) -> str:
    """The file's SHA-256, read in chunks: the results file can be hundreds of megabytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
