"""Executive view endpoints for the Playground Sandbox.

The headline tiles and the gaps card read the published results; the other cards, the graduation
tile and filtered tiles that aren't a published group are computed from the data model.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.sandbox.enrollment_trends.schemas import TermResponse
from app.sandbox.results.published import ResultsUnavailable

from . import course_load, export, home_states, results, supplemental
from .course_load import _active
from .schemas import (
    PROGRAM_PATTERN,
    AffinityFilter,
    AgeFilter,
    CohortLens,
    CourseLoadFilters,
    CourseLoadResponse,
    FirstGenFilter,
    GapsResponse,
    GenderFilter,
    GoalFilter,
    Granularity,
    HomeStateResponse,
    PellFilter,
    ProgramOption,
    RaceFilter,
    SupplementalResponse,
    TrendKpiResponse,
)

router = APIRouter(prefix="/sandbox/executive-view")


# Plain def: the database calls block, so FastAPI runs these in a worker thread.
def student_filters(
    goal: Annotated[GoalFilter, Query()] = "all",
    program: Annotated[str, Query(pattern=PROGRAM_PATTERN)] = "all",
    race: Annotated[RaceFilter, Query()] = "all",
    gender: Annotated[GenderFilter, Query()] = "all",
    age: Annotated[AgeFilter, Query()] = "all",
    pell: Annotated[PellFilter, Query()] = "all",
    first_gen: Annotated[FirstGenFilter, Query()] = "all",
    affinity: Annotated[AffinityFilter, Query()] = "all",
) -> CourseLoadFilters:
    """The page's student filters, read from the query string. "all" leaves a filter off."""
    return CourseLoadFilters(
        goal=goal,
        program=program,
        race=race,
        gender=gender,
        age=age,
        pell=pell,
        first_gen=first_gen,
        affinity=affinity,
    )


StudentFilters = Annotated[CourseLoadFilters, Depends(student_filters)]


@router.get("/kpis")
def kpis(
    filters: StudentFilters, cohort: Annotated[CohortLens, Query()] = "2024-25"
) -> TrendKpiResponse:
    """Return the headline rate for each shared measure, for one cohort or all pooled."""
    try:
        return results.get_kpis(cohort, filters)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/gaps")
def gaps(cohort: Annotated[CohortLens, Query()] = "2024-25") -> GapsResponse:
    """Return the largest equity gaps for each measure, for one cohort or all pooled."""
    try:
        return results.get_gaps(cohort)
    except ResultsUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.get("/headcount")
def headcount(filters: StudentFilters) -> TermResponse:
    """Return fall and spring headcount by entering cohort, worded for trend lines."""
    return results.get_headcount(filters)


@router.get("/course-load")
def course_load_curves(
    filters: StudentFilters,
    cohort: Annotated[CohortLens, Query()] = "2024-25",
    granularity: Annotated[Granularity, Query()] = "3",
) -> CourseLoadResponse:
    """Return year-1 credits curves for everyone and for the students who match the filters."""
    return course_load.get_course_load(cohort, filters, granularity)


@router.get("/course-load/programs")
def course_load_programs(cohort: Annotated[CohortLens, Query()] = "2024-25") -> list[ProgramOption]:
    """Return the programs the course load filter offers: 10 or more students, biggest first."""
    return course_load.get_programs(cohort)


@router.get("/home-states")
def home_state_counts(
    filters: StudentFilters, cohort: Annotated[CohortLens, Query()] = "2024-25"
) -> HomeStateResponse:
    """Return the matching students' headcount by home state, for one cohort or all pooled."""
    return home_states.get_home_states(cohort, _active(filters))


@router.get("/supplemental")
def supplemental_data(
    filters: StudentFilters, cohort: Annotated[CohortLens, Query()] = "2024-25"
) -> SupplementalResponse:
    """Return the uploaded supplemental attributes and their values, for the matching students."""
    return supplemental.get_supplemental(cohort, _active(filters))


ExportMeasure = Literal["retention", "persistence", "gateway_math", "gateway_english", "graduation"]


@router.get(
    "/kpis/students.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "One row per student"}},
)
def export_students(
    filters: StudentFilters,
    cohort: Annotated[CohortLens, Query()] = "2024-25",
    measure: Annotated[ExportMeasure | None, Query()] = None,
) -> Response:
    """Download the student IDs behind the headline measures, with each one's answers."""
    text = export.students_csv(cohort, _active(filters), measure)
    name = f"executive_view_students_{cohort}_{measure or 'all_measures'}.csv"
    return Response(
        content=text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
