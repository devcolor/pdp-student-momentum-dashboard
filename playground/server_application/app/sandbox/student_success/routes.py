"""Student success snapshot endpoints for the Playground Sandbox."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.sandbox.executive_view.schemas import CohortLens, TrendKpiResponse

from . import action_export, actions, equity, results
from .schemas import ActionResponse, EquityDimension, EquityResponse, School, TrendsResponse

router = APIRouter(prefix="/sandbox/student-success")


# Plain def: the database calls block, so FastAPI runs this in a worker thread.
@router.get("/kpis")
def kpis(cohort: Annotated[CohortLens, Query()] = "2024-25") -> TrendKpiResponse:
    """Return enrollment, retention, persistence, transfer and completion for one cohort lens."""
    return results.get_kpis(cohort)


@router.get("/trends")
def trends() -> TrendsResponse:
    """Return each of the five metrics for every entering cohort."""
    return results.get_trends()


@router.get("/equity")
def equity_analysis(
    cohort: Annotated[CohortLens, Query()] = "2024-25",
    dimension: Annotated[EquityDimension, Query()] = "race",
) -> EquityResponse:
    """Return population, programs and credit momentum split by one equity dimension."""
    return equity.get_equity(cohort, dimension)


@router.get("/actions")
def action_board(
    cohort: Annotated[CohortLens, Query()] = "2024-25",
    dimension: Annotated[EquityDimension, Query()] = "race",
    school: Annotated[School, Query()] = "ccac",
) -> ActionResponse:
    """Return the completion action tiles, their equity split and the hardest gateway courses."""
    return actions.get_actions(cohort, dimension, school)


ExportTile = Literal["stopped_out", "near_15", "gateway", "priority"]


@router.get(
    "/actions/students.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "One row per student"}},
)
def export_action_students(
    cohort: Annotated[CohortLens, Query()] = "2024-25",
    school: Annotated[School, Query()] = "ccac",
    tile: Annotated[ExportTile | None, Query()] = None,
) -> Response:
    """Download the student IDs behind the action board's tiles, flagged by the board's rules."""
    text = action_export.students_csv(cohort, school, tile)
    name = f"{school}_action_board_students_{cohort}_{tile or 'all_tiles'}.csv"
    return Response(
        content=text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
