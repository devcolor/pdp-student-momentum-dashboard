"""Every sandbox page's endpoints. main.py mounts this only when SANDBOX_ENABLED."""

from fastapi import APIRouter

from app.core.config import settings
from app.sandbox.add_a_sandbox_page import routes as add_a_sandbox_page
from app.sandbox.aid_momentum import routes as aid_momentum
from app.sandbox.associate_momentum import routes as associate_momentum
from app.sandbox.chart_examples import routes as chart_examples
from app.sandbox.chat import routes as chat
from app.sandbox.course_outcomes import routes as course_outcomes
from app.sandbox.credential_trends import routes as credential_trends
from app.sandbox.deaggregation import routes as deaggregation
from app.sandbox.dictionary import routes as dictionary
from app.sandbox.enrollment_trends import routes as enrollment_trends
from app.sandbox.executive_view import routes as executive_view
from app.sandbox.kpi_examples import routes as kpi_examples
from app.sandbox.measures import routes as measures
from app.sandbox.pipeline import routes as pipeline
from app.sandbox.results import routes as results
from app.sandbox.student_success import routes as student_success


def build_sandbox_router() -> APIRouter:
    """Every sandbox page's router, with the chat included only when its flag is on."""
    router = APIRouter(tags=["sandbox"])
    router.include_router(chart_examples.router)
    router.include_router(aid_momentum.router)
    router.include_router(dictionary.router)
    router.include_router(measures.router)
    # The chat is the only sandbox feature that calls a paid model, so it has its own flag.
    if settings.SANDBOX_CHAT_ENABLED:
        router.include_router(chat.router)
    router.include_router(kpi_examples.router)
    router.include_router(add_a_sandbox_page.router)
    router.include_router(pipeline.router)
    router.include_router(enrollment_trends.router)
    router.include_router(deaggregation.router)
    router.include_router(course_outcomes.router)
    router.include_router(credential_trends.router)
    router.include_router(associate_momentum.router)
    router.include_router(executive_view.router)
    router.include_router(results.router)
    router.include_router(student_success.router)
    return router


sandbox_router = build_sandbox_router()
