"""Request and response shapes for the results route.

They mirror the query builder's models in mcp/pdp_mcp/results.py. They're written out here, not
imported, because the API must start where that folder isn't available, and the OpenAPI file (and
the website's generated types) needs them when the app loads. tests/test_results_query.py fails if
the two ever differ.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_DIMENSIONS = 3
MAX_VALUE_LENGTH = 200  # keeps a where value inside SQLite's LIKE pattern limit


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuerySpec(_Model):
    """What to read. The manifest must approve each field; where filters within the breakdown."""

    measure: str = Field(description="A measure the manifest lists, such as gateway_math.")
    cohort: str = Field(
        description="An approved cohort grouping, such as '2021-22 + 2022-23 + 2023-24'."
    )
    group_by: list[str] = Field(
        min_length=1,
        max_length=MAX_DIMENSIONS,
        description="An approved breakdown, such as ['gender', 'race']. Order doesn't matter.",
    )
    where: dict[str, Annotated[str, Field(max_length=MAX_VALUE_LENGTH)]] = Field(
        default_factory=dict,
        description=(
            "Keep only groups with these values, e.g. {'gender': 'M'}. Keys must be in group_by."
        ),
    )
    include: list[Literal["rates", "gaps", "trends"]] = Field(
        default_factory=lambda: ["rates"],
        description=(
            "rates always; gaps adds each group's gap against everyone else; trends adds each "
            "row's change from the previous single cohort, worded as the page's tiles word it "
            "(trend_label)."
        ),
    )
    min_denominator: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Keep only groups whose published denominator is at least this. Hidden groups, "
            "whose denominator is blank, always drop out when it's set."
        ),
    )


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
    rank_by_affected: int | None = Field(
        default=None,
        description=(
            "The gap finder's rank among every group published for this measure and cohort, "
            "across all its breakdowns, by students affected (1 is the most behind). "
            "Not a rank within this breakdown alone."
        ),
    )
    rank_in_breakdown: int | None = Field(
        default=None,
        description=(
            "Rank among this breakdown's compared groups, 1 = most behind, by students affected. "
            "Ranked across the whole breakdown even when where narrows the rows; tied groups "
            "share a rank."
        ),
    )
    ranked_of: int | None = Field(
        default=None,
        description="How many of this breakdown's groups were compared and ranked.",
    )
    trend_vs: str | None = Field(
        default=None,
        description=(
            "With include trends: the previous single cohort the rate is compared with. Blank "
            "for a pool, for a hidden row or one hidden the year before, and for a year the "
            "manifest gives no trend (no_trend)."
        ),
    )
    trend_pct: float | None = Field(
        default=None,
        description="The relative change in the rate, in percent, to one decimal.",
    )
    trend_direction: str | None = Field(
        default=None, description="up, down or flat (a change under 1% is flat)."
    )
    trend_judgement: str | None = Field(
        default=None, description="good, bad or neutral, by which way is better."
    )
    trend_label: str | None = Field(
        default=None,
        description=(
            "The change as the tile's arrow says it, e.g. '−3.5% vs 2022-23'. Quote it as given."
        ),
    )


class Trend(_Model):
    """One published change from the previous single cohort, for a count rather than a rate."""

    vs: str
    pct: float
    direction: str
    judgement: str
    label: str


class QueryAnswer(_Model):
    """The slice a spec asked for, the everyone row to compare with, and the numbers' source."""

    spec: QuerySpec
    everyone: ResultRow
    rows: list[ResultRow]
    row_count: int
    truncated: bool
    max_rows: int | None = Field(
        description="The most rows an answer holds, or null when the caller read it uncapped."
    )
    entering_students_trend: Trend | None = Field(
        default=None,
        description=(
            "With include trends, for transfer_in_share and part_time_share: the change in "
            "entering students (the everyone row's denominator) from the previous single cohort. "
            "Blank otherwise."
        ),
    )
    data_loaded_at: str
    manifest_version: int
    source: Literal["synthetic"] = "synthetic"


class ApprovedMeasure(_Model):
    """The cohorts and breakdowns a spec may name for one measure."""

    cohorts: list[str]
    group_by: list[list[str]]


class ApprovedResponse(_Model):
    """Every approved measure, so a caller can build a spec the builder will accept."""

    measures: dict[str, ApprovedMeasure]
