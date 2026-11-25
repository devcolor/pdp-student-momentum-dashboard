"""Typed endpoints for the associate momentum page."""

from typing import Annotated

from fastapi import APIRouter, Query

from . import results
from .schemas import MilestoneResponse, MomentumResponse, NearCompleterResponse, Split, Window

router = APIRouter(prefix="/sandbox/associate-momentum")


@router.get("/milestones")
async def milestones(window: Annotated[Window, Query()] = "3") -> MilestoneResponse:
    """Among associate-seekers, the share who reached each credit milestone and the associate."""
    return results.get_milestones(window)


@router.get("/near-completers")
async def near_completers(
    window: Annotated[Window, Query()] = "3",
    split: Annotated[Split, Query()] = "credits_short",
) -> NearCompleterResponse:
    """Associate-seekers close to the credits for a degree but without one, by cohort."""
    return results.get_near_completers(window, split)


@router.get("/year-one")
async def year_one(window: Annotated[Window, Query()] = "3") -> MomentumResponse:
    """The associate within the window, by year-1 credits earned, against everyone else."""
    return results.get_year_one(window)
