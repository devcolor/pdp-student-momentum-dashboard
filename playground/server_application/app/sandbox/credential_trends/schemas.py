"""Response shapes and typed filters for the credential trends page."""

from typing import Literal

from pydantic import BaseModel

from app.sandbox.shared import ChartResponse

Credential = Literal["associate", "certificate"]
# "so_far" counts every credential the data has seen; the numbers are full years since entry.
Window = Literal["so_far", "1", "2", "3"]
FixedWindow = Literal["1", "2", "3"]
Factor = Literal[
    "gateway_math",
    "gateway_english",
    "enrollment_intensity",
    "enrollment_type",
    "pell",
    "age",
    "entry_term",
]
CohortStatus = Literal["ok", "too_new", "suppressed"]
GroupStatus = Literal["ok", "suppressed", "unknown_group"]


class CohortRateRow(BaseModel):
    """One credential's completion rate for one entering cohort."""

    cohort: str
    full_years_seen: int | None
    credential: str
    status: CohortStatus
    earned: int | None
    n: int | None
    rate: float | None
    ci_low: float | None
    ci_high: float | None


class CohortRateResponse(ChartResponse[CohortRateRow]):
    pass


class ProgramRow(BaseModel):
    """Students in one program who earned the credential, for one cohort."""

    cohort: str
    program: str
    earned: int | None
    cohort_earned: int | None


class ProgramResponse(ChartResponse[ProgramRow]):
    pass


class DriverRow(BaseModel):
    """One student group's completion rate, compared with everyone else who came for it."""

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


class DriverResponse(ChartResponse[DriverRow]):
    everyone_rate: float | None = None


class PathwayRow(BaseModel):
    """How many credential earners who came for one goal took one path."""

    sought: str
    pathway: str
    n: int | None
    share: float | None
    sought_total: int | None


class PathwayResponse(ChartResponse[PathwayRow]):
    pass
