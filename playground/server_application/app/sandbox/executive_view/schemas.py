"""Response shapes for the Sandbox executive view."""

from typing import Literal

from pydantic import BaseModel, Field

from app.sandbox.shared import ChartMeta, ChartResponse, Kpi, KpiResponse

CohortLens = Literal["all", "2021-22", "2022-23", "2023-24", "2024-25"]


class KpiTrend(BaseModel):
    """Which way a KPI moved, and whether that move is better, the same, or worse."""

    direction: Literal["up", "down", "flat"]
    status: Literal["good", "neutral", "bad"]
    label: str = Field(description='The relative change in words, e.g. "−3.5% vs 2022-23".')


class TrendKpi(Kpi):
    """A KPI tile with its cohort-to-cohort trend; trend is null with no earlier cohort rate."""

    trend: KpiTrend | None


class TrendKpiResponse(KpiResponse):
    """The headline KPIs, each with a trend."""

    items: list[TrendKpi]


class CohortShare(BaseModel):
    """How many students one cohort's own gap puts behind, for stacking a pooled bar."""

    cohort: str
    students_behind: int


class GapRow(BaseModel):
    """One student group behind everyone else on one measure; by_cohort is set when pooled."""

    measure: str
    group: str
    rate: float
    gap_pts: float
    n: int
    students_behind: int
    by_cohort: list[CohortShare] | None = None


class GapsResponse(ChartResponse[GapRow]):
    """The largest gaps for each measure, most students behind first."""


GoalFilter = Literal["all", "associate", "certificate", "other"]
RaceFilter = Literal[
    "all",
    "white",
    "hispanic",
    "black",
    "asian",
    "two_or_more",
    "nonresident",
    "american_indian",
    "pacific_islander",
    "unknown",
]
GenderFilter = Literal["all", "female", "male", "x", "unknown"]
AgeFilter = Literal["all", "20_and_younger", "over_20_to_24", "over_24", "unknown"]
PellFilter = Literal["all", "yes", "no", "unknown"]
FirstGenFilter = Literal["all", "yes", "no", "not_reported"]
AffinityFilter = Literal[
    "all",
    "none",
    "band",
    "choir",
    "theater",
    "football",
    "baseball",
    "basketball",
    "volleyball",
    "soccer",
    "student_government",
    "esports",
]
# A six-digit CIP code, "none" for no program recorded, or "all".
PROGRAM_PATTERN = r"^(all|none|\d{6})$"
# How many credits each band of the curve holds.
Granularity = Literal["1", "3", "6"]


class CourseLoadFilters(BaseModel):
    """Which students the course load curve counts. "all" leaves a filter off."""

    goal: GoalFilter = "all"
    program: str = Field(default="all", pattern=PROGRAM_PATTERN)
    race: RaceFilter = "all"
    gender: GenderFilter = "all"
    age: AgeFilter = "all"
    pell: PellFilter = "all"
    first_gen: FirstGenFilter = "all"
    affinity: AffinityFilter = "all"


class LoadCurve(BaseModel):
    """One group's share of students in each year-1 credits band. All null for a hidden group."""

    group: str
    n: int | None
    median_credits: float | None
    under_12_pct: float | None = Field(description="Percent attempting under 12 credits.")
    on_track_pct: float | None = Field(description="Percent attempting 30 credits or more.")
    shares: list[float | None] = Field(
        description="Percent of the group in each band, in the order of bands. Null when hidden."
    )


class ProgramOption(BaseModel):
    """A program the filter offers: its CIP code and the label to show."""

    code: str
    label: str


class CourseLoadResponse(BaseModel):
    """Year-1 course load for everyone, and for the students who match the filters, if any."""

    meta: ChartMeta
    bands: list[str]
    on_track_band: str = Field(description="The band holding the on-track credit level.")
    everyone: LoadCurve
    selected: LoadCurve | None = Field(description="Null when no filter is on.")
    hidden_reason: str | None = Field(description="Why the selected curve is hidden, if it is.")


class HomeStateRow(BaseModel):
    """One home state's matching students; n and share are null under 10 students."""

    state: str = Field(description='Two-letter state code, or "UNKNOWN".')
    n: int | None
    share: float | None = Field(description="Percent of the matching students.")


class HomeStateResponse(ChartResponse[HomeStateRow]):
    """Headcount by home state, biggest first."""


class SupplementalRow(BaseModel):
    """One student's uploaded values, and the term they belong to for a per-term file."""

    student_id: str
    academic_year: str | None
    academic_term: str | None
    values: dict[str, str | None] = Field(
        description="Each uploaded column's value; null if blank."
    )


class SupplementalFile(BaseModel):
    """One uploaded file, back in its own shape: a row per student (and term)."""

    file: str
    uploaded_on: str | None
    upload_id: str | None = Field(description="The upload's short id; null for an older upload.")
    per_term: bool
    columns: list[str] = Field(
        description="The uploaded columns, as attribute names, in file order."
    )
    students: int = Field(description="Matching students in the file.")
    total_rows: int = Field(description="Matching rows; at most 500 are sent.")
    rows: list[SupplementalRow]


class SupplementalResponse(BaseModel):
    """Every uploaded file, by name. Empty when nothing is uploaded."""

    meta: ChartMeta
    files: list[SupplementalFile]
