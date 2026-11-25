"""Response shapes for the course outcomes page."""

from typing import Literal

from pydantic import BaseModel

from app.sandbox.deaggregation.schemas import Gender, Race, Rate
from app.sandbox.shared import ChartResponse

# The pickers offer one race or gender, or "all" to leave that split out.
RaceChoice = Literal[Race, "all"]
GenderChoice = Literal[Gender, "all"]
Sort = Literal["difference", "group_dfw", "busiest"]


class CourseRow(BaseModel):
    """One course: its DFW rate for everyone, and for the chosen group when it's shown.

    When the group is everyone, group repeats everyone and difference_pts is blank.
    """

    course: str
    everyone: Rate
    group: Rate
    difference_pts: float | None


class CourseResponse(ChartResponse[CourseRow]):
    """DFW rate by course for everyone and for the chosen group."""

    cohort: str
    race: RaceChoice
    gender: GenderChoice
    # The group in words, e.g. "Black or African American students", "Women" or "Everyone".
    group_label: str
    min_enrollments: int
    courses_considered: int
    courses_with_group_hidden: int


class Comparison(BaseModel):
    """One rate for the chosen group beside everyone's, and the difference in points."""

    group: Rate
    everyone: Rate
    difference_pts: float | None


class MidtermAlertResponse(ChartResponse[CourseRow]):
    """Midterm alert rate by course, plus the overall alert and recovery rates for the group."""

    cohort: str
    race: RaceChoice
    gender: GenderChoice
    # The group in words, e.g. "Black or African American students", "Women" or "Everyone".
    group_label: str
    min_enrollments: int
    courses_considered: int
    courses_with_group_hidden: int
    alert: Comparison
    recovery: Comparison
