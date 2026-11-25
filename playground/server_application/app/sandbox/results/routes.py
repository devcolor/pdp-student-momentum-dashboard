"""The results route: a spec in, a slice of the published results out, via the query builder."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.errors import ErrorBody, ErrorResponse
from app.sandbox.chat.repo import RepoNotFound

from . import published
from .schemas import ApprovedResponse, QueryAnswer, QuerySpec

router = APIRouter(prefix="/sandbox/results")


def builder() -> tuple[Any, type]:
    """(reader, SpecRefused), or a 503 when the repository's query builder isn't available."""
    try:
        results = published.reader()
        from pdp_mcp.results import SpecRefused  # type: ignore[import-not-found]
    except (RepoNotFound, ImportError) as error:
        raise HTTPException(503, f"The query builder isn't available here: {error}") from error
    return results, SpecRefused


@router.post("/query")
def query(spec: QuerySpec, request: Request) -> QueryAnswer:
    """Read the slice of the published results that a manifest-approved spec asks for."""
    results, refused = builder()
    from pdp_mcp.results import Spec  # type: ignore[import-not-found]

    try:
        answer = results.query(Spec(**spec.model_dump()))
    except refused as error:
        return refusal(error, request)
    return QueryAnswer.model_validate(answer.model_dump())


@router.get("/approved")
def approved() -> ApprovedResponse:
    """Every measure with the cohorts and breakdowns a spec may name."""
    results, _ = builder()
    return ApprovedResponse(measures=results.approved())


def refusal(error: Any, request: Request) -> JSONResponse:
    """A refused spec in the API's error shape, with what is approved in details.

    A refusal that names approved options is the caller's to fix (400). One that names none is about
    the published file itself, such as results not published yet (503).
    """
    status = 400 if error.approved else 503
    body = ErrorBody(
        status=status,
        code="spec_refused" if status == 400 else "service_unavailable",
        message=str(error),
        path=request.url.path,
        details=[error.approved] if error.approved else None,
    )
    return JSONResponse(
        status_code=status, content=jsonable_encoder(ErrorResponse(error=body), exclude_none=True)
    )
