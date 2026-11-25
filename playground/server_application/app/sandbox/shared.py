"""Shared by every sandbox page: the response shapes and the mock terms and cohorts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.sandbox.results.schemas import QuerySpec

TERMS = ["Fall 23", "Spr 24", "Fall 24", "Spr 25", "Fall 25", "Spr 26"]
COHORT_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


class ChartMeta(BaseModel):
    # Defaulted fields are always in the response, so mark them required in its schema.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    title: str
    description: str
    takeaway: str | None = Field(default=None, description="One-sentence reading of the chart.")
    fields_used: list[str] = Field(description="AR file fields the numbers come from.")
    filters: list[str] = Field(default=[], description='Cohort filters, e.g. "Fall entry".')
    definitions: dict[str, str] = Field(default={}, description="How each measure is defined.")
    source: Literal["mock", "synthetic"] = "mock"
    specs: list[QuerySpec] = Field(
        default=[],
        description=(
            "The query_results specs this response was built from; empty when the page computes "
            "live. Pages read them uncapped, so a replay through query_results may come back "
            "truncated at 200 rows."
        ),
    )


class Kpi(BaseModel):
    # Defaulted fields are always in the response, so mark them required in its schema.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    id: str
    label: str
    unit: Literal["percent", "split", "terms", "count"]
    value: float
    secondary_value: float | None = Field(
        default=None, description='Second half of a split, e.g. 36 in "64 / 36".'
    )
    detail: str


class KpiResponse(BaseModel):
    meta: ChartMeta
    items: list[Kpi]


class ChartResponse[RowT: BaseModel](BaseModel):
    """Every chart endpoint answers with its meta plus one row per point or bar."""

    meta: ChartMeta
    rows: list[RowT]
