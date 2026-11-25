"""Enrollment trends endpoints for the Playground Sandbox, computed from the data model."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.sandbox.executive_view.schemas import TrendKpiResponse

from . import kpis as kpi_results
from . import results
from .schemas import EnteringResponse, SplitBy, TermResponse

router = APIRouter(prefix="/sandbox/enrollment-trends")


# Plain def: the database call blocks, so FastAPI runs these in a worker thread.
@router.get("/entering")
def entering(split_by: Annotated[SplitBy, Query()] = "enrollment_type") -> EnteringResponse:
    """Return entering students per cohort, split by one student group."""
    return results.get_entering(split_by)


@router.get("/by-term")
def by_term() -> TermResponse:
    """Return fall and spring headcount by entering cohort."""
    return results.get_by_term()


@router.get("/kpis")
def kpis() -> TrendKpiResponse:
    """Return the latest entering cohort's enrollment KPIs, with trends."""
    return kpi_results.get_kpis()
