"""Response shapes for the Sandbox enrollment trends page."""

from typing import Literal

from pydantic import BaseModel

from app.sandbox.shared import ChartResponse

SplitBy = Literal["enrollment_type", "enrollment_intensity", "pell", "entry_term"]


class EnteringRow(BaseModel):
    """One student group's size within one entering cohort; n and share are null if suppressed."""

    cohort: str
    group: str
    n: int | None
    share: float | None
    cohort_total: int


class EnteringResponse(ChartResponse[EnteringRow]):
    """Entering students per cohort, split by one student group."""


class TermRow(BaseModel):
    """One entering cohort's headcount in one term; n is null if suppressed."""

    term: str
    cohort: str
    n: int | None
    term_total: int


class TermResponse(ChartResponse[TermRow]):
    """Fall and spring headcount, one row per term and entering cohort."""
