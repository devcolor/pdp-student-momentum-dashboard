"""One measure by unmet need band, its ranked gaps, and Pell beside it, from the query builder.

The bands come from the synthetic financial aid enrichment, whose relationship with Retention is
planted. The numbers are the builder's answers over the published results: no SQL and no live
measure runs here. Where the bands come from is read from the data model's stored rows rather than
written in here, so the page can never claim more than the data behind it.
"""

from app.sandbox.chat import query_tool
from app.sandbox.results.published import page_answer
from app.sandbox.results.schemas import QueryAnswer, QuerySpec, ResultRow
from app.sandbox.shared import ChartMeta

from .schemas import (
    BANDS,
    GAP_MEASURES,
    BandGapRow,
    BandGapsResponse,
    BandRow,
    BandsResponse,
    Measure,
    PellResponse,
    PellRow,
)

# The page pools three cohorts: a single cohort's band x race slices can be recovered by
# subtraction, and pooling keeps every band well above the ten-student threshold.
COHORT_YEARS = ("2021-22", "2022-23", "2023-24")
COHORT = " + ".join(COHORT_YEARS)
DIMENSION = "unmet_need_band"
PELL_LABELS = {"Y": "Pell recipients", "N": "No Pell", "UNKNOWN": "Pell unknown"}

MEASURE_LABELS = {
    "retention": "Retention",
    "persistence": "Persistence elsewhere",
    "gateway_math": "Gateway math, year 1",
    "gateway_english": "Gateway English, year 1",
    "dfw_rate": "DFW rate",
    "credit_completion": "Credit completion",
}
# A higher rate is worse for these, so the page can word the reading correctly.
LOWER_IS_BETTER = {"dfw_rate"}

PROVENANCE = """
SELECT DISTINCT source FROM student_attribute WHERE attribute_key = ? ORDER BY source
"""


def _provenance() -> str | None:
    """What the stored aid rows say about where they came from, or None when that can't be read.

    It's metadata, not a number, so the page never fails over it.
    """
    try:
        with query_tool.backend().connect() as connection:
            rows = connection.execute(PROVENANCE, (DIMENSION,)).fetchall()
    except Exception:
        return None
    return "; ".join(str(row[0]) for row in rows) or None


def _definitions(measure: Measure, source: str | None) -> dict[str, str]:
    """The measure's definition, plus what the aid data is and what it is not."""
    definitions = {
        "Unmet need": (
            "Cost of attendance minus EFC and all grants, banded. Read for the cohort year."
        ),
        "UNKNOWN band": "No ISIR record, so there is no EFC to compute a need from. Not a zero.",
    }
    if measure in LOWER_IS_BETTER:
        definitions["Reading this"] = (
            "A higher rate is worse here, so a band above everyone is behind."
        )
    if source:
        definitions["Where the bands come from"] = source
    definitions["Planted effect"] = (
        "The gradient below is built into the synthetic aid file, not discovered in it. "
        "Regenerating with --effect 0 flattens it. Nothing here is a finding about "
        "real students."
    )
    return definitions


def _rate(row: ResultRow | None) -> tuple[float | None, float | None]:
    """A published row as a percentage and its denominator. Missing or hidden groups stay blank."""
    if row is None or row.metric_rate is None:
        return None, None
    return round(row.metric_rate * 100, 1), row.denominator


def _spec(measure: Measure, dimension: str, include_gaps: bool = False) -> QuerySpec:
    """One measure by one dimension for the pooled cohort."""
    return QuerySpec(
        measure=measure,
        cohort=COHORT,
        group_by=[dimension],
        include=["rates", "gaps"] if include_gaps else ["rates"],
    )


def _by_value(answer: QueryAnswer, dimension: str) -> dict[str, ResultRow]:
    """An answer's rows keyed by the dimension's value."""
    return {row.group[dimension]: row for row in answer.rows}


def get_bands(measure: Measure) -> BandsResponse:
    """One measure by unmet need band, with everyone as the reference row."""
    spec = _spec(measure, DIMENSION)
    answer = page_answer(spec)
    by_band = _by_value(answer, DIMENSION)

    rows = []
    for band in BANDS:
        rate, n = _rate(by_band.get(band))
        rows.append(BandRow(band=band, rate=rate, n=n))
    rate, n = _rate(answer.everyone)
    rows.append(BandRow(band="everyone", rate=rate, n=n, is_everyone=True))

    # The spread is worked out here for display, and is not tested for noise.
    shown = [row for row in rows if row.rate is not None and not row.is_everyone]
    takeaway = None
    if len(shown) >= 2:
        worst, best = max(shown, key=lambda r: r.rate), min(shown, key=lambda r: r.rate)
        if measure in LOWER_IS_BETTER:
            worst, best = best, worst
        spread = round(abs(worst.rate - best.rate), 1)
        takeaway = (
            f"{spread} points separate the {best.band} and {worst.band} bands (not tested for "
            "noise). The aid file plants that gradient, so read it as the chart working, not as "
            "evidence."
        )
    return BandsResponse(
        meta=ChartMeta(
            title=f"{MEASURE_LABELS[measure]} by unmet need",
            description="One measure per unmet need band, with every student as the reference.",
            takeaway=takeaway,
            fields_used=["success_measures", "student_attribute.unmet_need_band"],
            filters=[f"Measure: {MEASURE_LABELS[measure]}", f"Cohorts {COHORT}, pooled"],
            definitions=_definitions(measure, _provenance()),
            source="synthetic",
            specs=[spec],
        ),
        rows=rows,
    )


def get_gaps(measure: Measure) -> BandGapsResponse:
    """The ranked gaps for one measure, or no rows when the gap finder doesn't test it."""
    rows: list[BandGapRow] = []
    specs: list[QuerySpec] = []
    if measure not in GAP_MEASURES:
        takeaway = (
            f"The gap finder doesn't test {MEASURE_LABELS[measure]}: its statistics need an answer "
            "that is a yes or no per student. Use the bands chart for this measure."
        )
    else:
        spec = _spec(measure, DIMENSION, include_gaps=True)
        specs.append(spec)
        # Only compared (ok) gaps have numbers; the builder ranks them within the bands alone.
        compared = [row for row in page_answer(spec).rows if row.gap_status == "ok"]
        compared.sort(key=lambda row: row.rank_in_breakdown or 0)
        rows = [
            BandGapRow(
                band=row.group[DIMENSION],
                gap_pts=row.gap_pts,
                ci_low=row.ci_low,
                ci_high=row.ci_high,
                q_value=row.q_value,
                likely_noise=bool(row.likely_noise),
                rank=row.rank_in_breakdown,
                ranked_of=row.ranked_of,
            )
            for row in compared
        ]
        tested = [row for row in rows if not row.likely_noise]
        if rows:
            takeaway = (
                f"{len(tested)} of {len(rows)} band gaps clear the noise check. "
                "A gap whose interval crosses zero is not called a finding."
            )
        else:
            takeaway = f"No saved band gaps for {MEASURE_LABELS[measure]} on these cohorts yet."

    return BandGapsResponse(
        meta=ChartMeta(
            title=f"{MEASURE_LABELS[measure]}: band gaps, most students behind first",
            description="Each band against everyone else, with a 95% interval and a noise check.",
            takeaway=takeaway,
            fields_used=["equity_gaps"],
            filters=[
                f"Measure: {MEASURE_LABELS[measure]}",
                f"Cohorts {COHORT}, pooled",
                "Hidden groups left out",
            ],
            definitions={
                "Likely noise": (
                    "The gap's 95% interval crosses zero once corrected for many tests."
                ),
                "q-value": "The p-value corrected for how many gaps were tested together.",
            },
            source="synthetic",
            specs=specs,
        ),
        rows=rows,
    )


def get_pell(measure: Measure) -> PellResponse:
    """Pell status beside the unmet need bands: one real field against the synthetic one."""
    pell_spec, band_spec = _spec(measure, "pell"), _spec(measure, DIMENSION)
    by_pell = _by_value(page_answer(pell_spec), "pell")
    by_band = _by_value(page_answer(band_spec), DIMENSION)

    rows = []
    for value, label in PELL_LABELS.items():
        rate, n = _rate(by_pell.get(value))
        rows.append(PellRow(group=label, rate=rate, n=n, series="pell", is_real=True))
    for band in BANDS:
        rate, n = _rate(by_band.get(band))
        rows.append(PellRow(group=band, rate=rate, n=n, series="unmet_need_band", is_real=False))

    definitions = _definitions(measure, _provenance())
    definitions["Pell_Status_First_Year"] = (
        "Real mock data, and the only aid field in it: Y or N per student. 7.4% of rows hold U, "
        "which the dictionary doesn't define, so they count as unknown."
    )
    return PellResponse(
        meta=ChartMeta(
            title=f"{MEASURE_LABELS[measure]}: one binary against four bands",
            description=(
                "What a Pell flag can tell you, next to what a graded need measure can. "
                "Pell is the only aid field in the mock data; the bands stand in for the "
                "file that is missing."
            ),
            takeaway=(
                "Pell splits students two ways and cannot separate a student $500 short from one "
                "$8,000 short. The bands are synthetic, so this compares what each field "
                "could say, not what either one says about students."
            ),
            fields_used=["Pell_Status_First_Year", "student_attribute.unmet_need_band"],
            filters=[f"Measure: {MEASURE_LABELS[measure]}", f"Cohorts {COHORT}, pooled"],
            definitions=definitions,
            source="synthetic",
            specs=[pell_spec, band_spec],
        ),
        rows=rows,
    )
