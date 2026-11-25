"""Unmet need and momentum endpoints for the Playground Sandbox, read from the published results."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.sandbox.results.published import ResultsUnavailable

from . import results
from .schemas import BandGapsResponse, BandsResponse, Measure, PellResponse

router = APIRouter(prefix="/sandbox/aid-momentum")


# Plain def: the results file is read with blocking calls, so FastAPI runs these in a worker thread.
@router.get("/bands")
def bands(measure: Annotated[Measure, Query()] = "retention") -> BandsResponse:
    """Return one measure for each unmet need band, with everyone as the reference row."""
    try:
        return results.get_bands(measure)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/gaps")
def gaps(measure: Annotated[Measure, Query()] = "retention") -> BandGapsResponse:
    """Return the gap finder's ranked band gaps for one measure."""
    try:
        return results.get_gaps(measure)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/pell")
def pell(measure: Annotated[Measure, Query()] = "retention") -> PellResponse:
    """Return Pell status beside the unmet need bands, for one measure."""
    try:
        return results.get_pell(measure)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
