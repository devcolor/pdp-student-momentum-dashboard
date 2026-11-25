"""Response shapes for the student success trends."""

from typing import Literal

from pydantic import BaseModel, Field

from app.sandbox.executive_view.schemas import KpiTrend
from app.sandbox.shared import ChartMeta, ChartResponse


class TrendRow(BaseModel):
    """One metric for one entering cohort. value, numerator and n are null when suppressed."""

    metric: str = Field(description="Metric id, the same as the snapshot KPI ids.")
    label: str
    unit: str = Field(description='"count" for enrollment, "percent" for the rates.')
    cohort: str
    value: float | None
    numerator: int | None
    n: int | None
    partial: bool = Field(description="True when the cohort hasn't had the full window yet.")


class TrendsResponse(ChartResponse[TrendRow]):
    """Each of the five metrics for every entering cohort, oldest first."""


EquityDimension = Literal["race", "gender", "age_band", "first_gen", "pell"]

# Which university's action board: MVSU's drops the associate tile and words gateway next steps.
School = Literal["ccac", "mvsu"]


class EquityGroup(BaseModel):
    """One equity group's size, retention gap and year-1 credit milestones. Null when hidden."""

    group: str
    n: int | None
    share: float | None = Field(description="Percent of the cohort lens.")
    retention: float | None
    retention_gap_pts: float | None = Field(description="Group minus everyone else, in points.")
    likely_noise: bool | None
    milestones: list[float | None] = Field(description="Percent reaching each credit milestone.")


class ProgramSegment(BaseModel):
    """One group's students in one program; n is null under the display threshold."""

    group: str
    n: int | None


class EquityProgram(BaseModel):
    """One of the largest programs, split by the selected dimension."""

    code: str
    label: str
    n: int
    segments: list[ProgramSegment]


class EquityResponse(BaseModel):
    """The three views of the Student Success & Equity Analysis card."""

    meta: ChartMeta
    milestones: list[str]
    groups: list[EquityGroup]
    everyone: EquityGroup
    programs: list[EquityProgram]


class ActionTile(BaseModel):
    """One action: how many students, what it means, and the suggested next step."""

    id: str
    label: str
    value: int | None = Field(description="Students; null under the display threshold.")
    share: float | None = Field(description="Percent of the cohort lens.")
    detail: str
    action: str
    trend: KpiTrend | None = Field(
        default=None, description="Change in share from the prior cohort; down is better."
    )


class ActionGroupRow(BaseModel):
    """One equity group's count in each action. Null when under the display threshold."""

    group: str
    n: int | None
    stopped_out: int | None
    near_15: int | None
    gateway: int | None
    priority: int | None


class GatewayCourseRow(BaseModel):
    """One gateway course's DFW rate."""

    course: str
    subject: str
    dfw_rate: float
    n: int


class ActionResponse(BaseModel):
    """The Student Completion Action Board."""

    meta: ChartMeta
    tiles: list[ActionTile]
    groups: list[ActionGroupRow]
    gateway_courses: list[GatewayCourseRow]
