"""The course outcomes endpoints: DFW by course, and the planted midterm alerts."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.sandbox.results.published import ResultsUnavailable

from . import results
from .schemas import CourseResponse, GenderChoice, MidtermAlertResponse, RaceChoice, Sort

router = APIRouter(prefix="/sandbox/course-outcomes")


# Plain def: the results file is read with blocking calls, so FastAPI runs these in a worker thread.
@router.get("/dfw")
def dfw(
    race: Annotated[RaceChoice, Query()] = "Black or African American",
    gender: Annotated[GenderChoice, Query()] = "M",
    min_enrollments: Annotated[int, Query(ge=10, le=2000)] = 200,
    sort: Annotated[Sort, Query()] = "difference",
) -> CourseResponse:
    """DFW rate by course for everyone and for the chosen race and gender (either can be all)."""
    try:
        return results.get_courses(race, gender, min_enrollments, sort)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/midterm-alerts")
def midterm_alerts(
    race: Annotated[RaceChoice, Query()] = "Black or African American",
    gender: Annotated[GenderChoice, Query()] = "M",
    min_enrollments: Annotated[int, Query(ge=10, le=2000)] = 200,
) -> MidtermAlertResponse:
    """The planted midterm alert rate by course, with alert and recovery for the group."""
    try:
        return results.get_midterm_alerts(race, gender, min_enrollments)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
