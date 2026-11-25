"""Response shapes for the Sandbox unmet need and momentum page."""

from typing import Literal

from pydantic import BaseModel, Field

from app.sandbox.shared import ChartResponse

# Every shared measure. The gap finder only tests the four that are a yes or no per student.
Measure = Literal[
    "retention", "persistence", "gateway_math", "gateway_english", "dfw_rate", "credit_completion"
]
GAP_MEASURES = ("retention", "persistence", "gateway_math", "gateway_english")

# The bands the financial aid enrichment stores, driest first, with UNKNOWN last.
BANDS = ("$0", "$1-2k", "$2-5k", "$5k+", "UNKNOWN")


class BandRow(BaseModel):
    """One unmet need band's rate on one measure. A hidden band keeps rate and n null."""

    band: str
    rate: float | None
    n: int | None
    is_everyone: bool = Field(default=False, description="True for the all-students reference row.")


class BandsResponse(ChartResponse[BandRow]):
    """One measure by unmet need band, with everyone as the last row."""


class BandGapRow(BaseModel):
    """One band's gap from everyone else, as the gap finder ranked it."""

    band: str
    gap_pts: float
    ci_low: float
    ci_high: float
    q_value: float
    likely_noise: bool
    rank: int
    ranked_of: int


class BandGapsResponse(ChartResponse[BandGapRow]):
    """The ranked gaps for one measure, or no rows when the gap finder doesn't test it."""


class PellRow(BaseModel):
    """One Pell status or unmet need band on one measure, tagged by which data it came from."""

    group: str
    rate: float | None
    n: int | None
    series: Literal["pell", "unmet_need_band"]
    is_real: bool = Field(
        description="True for Pell, which is in the mock data. False for the aid file."
    )


class PellResponse(ChartResponse[PellRow]):
    """Pell status beside the unmet need bands, for the same measure."""
