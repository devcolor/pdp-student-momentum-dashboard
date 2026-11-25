"""Response shapes for the de-aggregation page."""

from typing import Literal

from pydantic import BaseModel

from app.sandbox.shared import ChartResponse

Race = Literal[
    "American Indian or Alaska Native",
    "Asian",
    "Black or African American",
    "Hispanic",
    "Native Hawaiian or Other Pacific Islander",
    "Nonresident alien",
    "Two or More Races",
    "White",
]
Gender = Literal["M", "F"]


class Rate(BaseModel):
    """A shown group's rate as a percentage, and how many it counts. Both blank when hidden."""

    rate: float | None
    n: int | None


class OutcomeRow(BaseModel):
    """One measure for the chosen group, beside the other gender of the same race and everyone."""

    measure: str
    label: str
    counts: Literal["students", "enrollments"]
    lower_is_better: bool
    group: Rate
    other_gender: Rate
    everyone: Rate
    gap_pts: float | None
    ci_low: float | None
    ci_high: float | None
    likely_noise: bool | None
    rank: int | None
    ranked_of: int | None
    not_tested: str | None


class OutcomeResponse(ChartResponse[OutcomeRow]):
    cohort: str
    race: Race
    gender: Gender
