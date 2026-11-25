"""The de-aggregation endpoint."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.sandbox.results.published import ResultsUnavailable

from . import results
from .schemas import Gender, OutcomeResponse, Race

router = APIRouter(prefix="/sandbox/deaggregation")


# Plain def: the results file is read with blocking calls, so FastAPI runs this in a worker thread.
@router.get("/outcomes")
def outcomes(
    race: Annotated[Race, Query()] = "Black or African American",
    gender: Annotated[Gender, Query()] = "M",
) -> OutcomeResponse:
    """Every success measure for one race x gender group."""
    try:
        return results.get_outcomes(race, gender)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
