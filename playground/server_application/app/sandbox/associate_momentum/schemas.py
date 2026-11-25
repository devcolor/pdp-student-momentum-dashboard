"""Response shapes and typed filters for the associate momentum page."""

from typing import Literal

from pydantic import BaseModel

from app.sandbox.shared import ChartResponse

# Full years since entry. One year is too short to reach the later milestones or an associate.
Window = Literal["2", "3"]
Split = Literal["credits_short", "enrollment", "intensity"]
CellStatus = Literal["ok", "suppressed"]
GroupStatus = Literal["ok", "suppressed", "unknown_group"]


class MilestoneRow(BaseModel):
    """The share of one cohort's associate-seekers who reached one milestone within the window."""

    cohort: str
    milestone: str
    status: CellStatus
    reached: int | None
    n: int | None
    rate: float | None


class MilestoneResponse(ChartResponse[MilestoneRow]):
    pass


class NearCompleterRow(BaseModel):
    """Near-completers in one part of one cohort, with the cohort's whole pool."""

    cohort: str
    part: str
    count: int | None
    share_of_pool: float | None
    pool: int | None
    seekers: int | None
    pool_rate: float | None


class NearCompleterResponse(ChartResponse[NearCompleterRow]):
    pass


class MomentumRow(BaseModel):
    """One year-1 credit band's associate rate, compared with every other associate-seeker."""

    group: str
    status: GroupStatus
    earned: int | None
    n: int | None
    rate: float | None
    comparison_rate: float | None
    gap_pts: float | None
    ci_low: float | None
    ci_high: float | None
    likely_noise: bool | None


class MomentumResponse(ChartResponse[MomentumRow]):
    everyone_rate: float | None = None
