"""Typed endpoints for the credential trends page."""

from typing import Annotated

from fastapi import APIRouter, Query

from . import results
from .schemas import (
    CohortRateResponse,
    Credential,
    DriverResponse,
    Factor,
    FixedWindow,
    PathwayResponse,
    ProgramResponse,
    Window,
)

router = APIRouter(prefix="/sandbox/credential-trends")


@router.get("/by-cohort")
async def by_cohort(window: Annotated[Window, Query()] = "so_far") -> CohortRateResponse:
    """Associate and certificate rates per cohort, counted so far or within a fixed window."""
    return results.get_by_cohort(window)


@router.get("/by-program")
async def by_program(
    credential: Annotated[Credential, Query()] = "certificate",
    window: Annotated[FixedWindow, Query()] = "1",
) -> ProgramResponse:
    """Who earned the credential within the window, by program, for each cohort that has had it."""
    return results.get_by_program(credential, window)


@router.get("/drivers")
async def drivers(
    credential: Annotated[Credential, Query()] = "associate",
    window: Annotated[FixedWindow, Query()] = "3",
    factor: Annotated[Factor, Query()] = "gateway_math",
) -> DriverResponse:
    """Among students who came for the credential, which groups finish it more or less often."""
    return results.get_drivers(credential, window, factor)


@router.get("/pathways")
async def pathways(window: Annotated[FixedWindow, Query()] = "3") -> PathwayResponse:
    """For students who earned a credential, whether it was an associate, a certificate, or both."""
    return results.get_pathways(window)
