"""/sandbox/chat: the question in, and the assistant's grounded answer out."""

import json
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from app.sandbox.executive_view.cohorts import SINGLE_YEARS
from app.sandbox.executive_view.schemas import CohortLens
from app.sandbox.results.schemas import QuerySpec

from . import context, presidential

Prompt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
PageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

# Caps on the history a client may send. They bound the cost of a long conversation and the size
# of the input the model is asked to trust. A turn is allowed to be longer than a prompt because
# an assistant turn is a whole answer, and MAX_TOKENS of output is more than 2000 characters.
MAX_TURNS = 10
MAX_TURN_CHARS = 8_000
MAX_HISTORY_CHARS = 12_000

TurnContent = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TURN_CHARS)
]


class Turn(BaseModel):
    """One earlier turn of the same conversation, as the client recorded it."""

    role: Literal["user", "assistant"]
    content: TurnContent


# The most a count on the presidential view can be: far above any entering cohort's size.
MAX_COUNT = 1_000_000


class TrendPoint(BaseModel):
    """One entering cohort's point on a presidential view card's trend line, as the page drew it."""

    model_config = ConfigDict(extra="forbid")

    cohort: CohortLens
    # Null when the point is hidden or not observable yet.
    value: float | None = Field(ge=0, le=MAX_COUNT)
    # True when the cohort hasn't had every year the card needs; the page draws it dashed.
    partial: bool

    @field_validator("cohort")
    @classmethod
    def _one_cohort(cls, cohort: str) -> str:
        """Refuse the pooled lens: a trend line has one point per entering cohort."""
        if cohort == "all":
            raise ValueError("a trend point is one entering cohort, not 'all'")
        return cohort


# One point per entering cohort the trend lines draw.
MAX_TREND_POINTS = len(SINGLE_YEARS)


class KeywordContext(BaseModel):
    """The thing on the executive or presidential view a question came from.

    Every name is checked against what the page can actually render, in the validator below. The
    numbers are carried so the seed sentence can quote the figure the staff member is looking at.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["measure", "group", "cohort"]
    measure: str | None = None
    group: str | None = None
    cohort: str | None = None
    rate: float | None = None
    gap_pts: float | None = None
    n: int | None = None
    # A tile with a student filter on is calculated live; unfiltered tiles and gaps are published.
    filtered: bool = False
    # Older clients send no view: they are all on the executive view.
    view: Literal["executive-view", "presidential-view"] = "executive-view"
    # The clicked presidential card's trend line, oldest first. Always empty on the executive view.
    trend: list[TrendPoint] = Field(default_factory=list, max_length=MAX_TREND_POINTS)

    @model_validator(mode="after")
    def _check_names(self) -> Self:
        """Refuse any name, number or trend the page the keyword came from can't show."""
        if self.view == "presidential-view":
            return self._check_presidential()
        if self.trend:
            raise ValueError("only a presidential view keyword carries a trend")
        if self.measure is not None and self.measure not in context.allowed_measures():
            raise ValueError(f"{self.measure!r} is not a measure on the executive view")
        if self.group is not None and self.group not in context.allowed_groups():
            raise ValueError(f"{self.group!r} is not a group on the executive view")
        if self.cohort is not None and self.cohort not in context.allowed_cohorts():
            raise ValueError(f"{self.cohort!r} is not a cohort on the executive view")
        if self.kind in ("measure", "group") and self.measure is None:
            raise ValueError(f"a {self.kind} keyword needs a measure")
        if self.kind == "group" and self.group is None:
            raise ValueError("a group keyword needs a group")
        if self.kind == "cohort" and self.cohort is None:
            raise ValueError("a cohort keyword needs a cohort")
        return self

    def _check_presidential(self) -> Self:
        """One card on the presidential view: its label, its value in the right field, its trend."""
        if self.kind != "measure" or self.measure is None:
            raise ValueError("a presidential view keyword is a measure keyword with a measure")
        if self.measure not in presidential.allowed_measures():
            raise ValueError(f"{self.measure!r} is not a measure on the presidential view")
        if self.cohort is not None and self.cohort not in context.allowed_cohorts():
            raise ValueError(f"{self.cohort!r} is not a cohort on the presidential view")
        if self.group is not None or self.gap_pts is not None:
            raise ValueError("the presidential view has no groups or gaps")
        if self.filtered:
            raise ValueError("the presidential view has no student filters")
        self._check_card_value()
        self._check_trend()
        return self

    def _check_card_value(self) -> None:
        """Enrollment's value is a count in n; every other card's is a percent in rate."""
        if presidential.is_count(self.measure):
            if self.rate is not None:
                raise ValueError(f"{self.measure} is a count: send its value as n, not rate")
            if self.n is not None and not 0 <= self.n <= MAX_COUNT:
                raise ValueError(f"n must be between 0 and {MAX_COUNT:,}")
            return
        if self.n is not None:
            raise ValueError(f"{self.measure} is a percent: send its value as rate, not n")
        values = [self.rate, *(point.value for point in self.trend)]
        if any(value is not None and not 0 <= value <= 100 for value in values):
            raise ValueError(f"{self.measure} is a percent, so its values are from 0 to 100")

    def _check_trend(self) -> None:
        """The card's trend line: at least one point, each cohort once, oldest first."""
        if not self.trend:
            raise ValueError("a presidential view keyword needs the card's trend")
        cohorts = [point.cohort for point in self.trend]
        if len(set(cohorts)) != len(cohorts):
            raise ValueError("each cohort can be in the trend only once")
        if cohorts != sorted(cohorts, key=SINGLE_YEARS.index):
            raise ValueError("the trend runs oldest cohort first")


MAX_PAGE_FILTERS = 12
# The executive view's gaps card reads 15 specs, one per measure and breakdown.
MAX_PAGE_SPECS = 16
# QuerySpec's strings and where keys are unbounded (it must equal the MCP Spec), so the page context
# caps the specs' total size instead. The de-aggregation page's 8 specs take about 1,500 characters.
MAX_PAGE_SPECS_CHARS = 4000


def compact_json(value: Any) -> str:
    """Compact JSON with < escaped, so client-supplied text can't close the page_context tag."""
    return json.dumps(value, separators=(",", ":")).replace("<", "\\u003c")


def spec_json(spec: QuerySpec) -> str:
    """One spec as the page context block shows it: compact JSON without its default fields."""
    return compact_json(spec.model_dump(mode="json", exclude_defaults=True))


class PageContext(BaseModel):
    """What the user is looking at when they ask: the page's title, filter chips and specs."""

    title: PageText = Field(description="The page or chart title the user sees.")
    filters: list[PageText] = Field(
        default_factory=list,
        max_length=MAX_PAGE_FILTERS,
        description="The filter chips the user sees, e.g. 'Race: Black or African American'.",
    )
    # Checked for shape only: the query builder refuses an unapproved spec if the model replays it.
    specs: list[QuerySpec] = Field(
        default_factory=list,
        max_length=MAX_PAGE_SPECS,
        description=(
            "The query_results specs behind the page's numbers. Empty when the page computes "
            "its numbers live instead of reading the published results."
        ),
    )

    @field_validator("specs")
    @classmethod
    def _specs_fit(cls, specs: list[QuerySpec]) -> list[QuerySpec]:
        """Refuse specs whose JSON, as the context block writes it, is over MAX_PAGE_SPECS_CHARS."""
        size = sum(len(spec_json(spec)) for spec in specs)
        if size > MAX_PAGE_SPECS_CHARS:
            # Not ValueError: its exception object in ctx can't go out in the 422 body.
            raise PydanticCustomError(
                "specs_too_long",
                "specs take {size} characters; the most is {limit}",
                {"size": size, "limit": MAX_PAGE_SPECS_CHARS},
            )
        return specs


class SuggestRequest(BaseModel):
    """One staff question, the turns before it, the keyword it came from, and the page it's on."""

    prompt: Prompt
    # The conversation so far, oldest first. The client holds it; the server keeps nothing.
    turns: list[Turn] = []
    context: KeywordContext | None = None
    page: PageContext | None = Field(
        default=None, description="The page the user is viewing, so the answer starts from it."
    )

    @model_validator(mode="after")
    def _check_turns(self) -> Self:
        if len(self.turns) > MAX_TURNS:
            raise ValueError(f"at most {MAX_TURNS} earlier turns, not {len(self.turns)}")
        total = sum(len(turn.content) for turn in self.turns)
        if total > MAX_HISTORY_CHARS:
            raise ValueError(f"at most {MAX_HISTORY_CHARS} characters of history, not {total}")
        # The model's API needs user and assistant to alternate, and prompt is the next user turn,
        # so the history has to start with user and end with assistant.
        expected = ["user", "assistant"] * (len(self.turns) // 2 + 1)
        if [turn.role for turn in self.turns] != expected[: len(self.turns)]:
            raise ValueError("turns must alternate, starting with user")
        if self.turns and self.turns[-1].role != "assistant":
            raise ValueError("the last turn must be the assistant's, because prompt follows it")
        return self


class ToolResult(BaseModel):
    """One tool call the assistant made, with its result or MCP-shaped error."""

    tool: str
    input: dict[str, Any]
    output: dict[str, Any]
    is_error: bool = False
    sql: str | None = Field(
        default=None,
        description=(
            "The SQL the query builder ran, for staff to rerun on the published results. "
            "Only on a query_results call that answered."
        ),
    )


LinkedPage = Literal["deaggregation", "course-outcomes", "aid-momentum", "student-success"]


class PageLink(BaseModel):
    """A page showing what an answer read. The client builds the address; the server sends none."""

    page: LinkedPage
    label: str = Field(description="The link text, written by the server from its own labels.")
    params: dict[str, str] = Field(
        description="The page's picker values, each from its picker's list, e.g. {'race': 'Asian'}."
    )


class SuggestResponse(BaseModel):
    """The assistant's answer, plus the tool results it was grounded on."""

    # Fields with defaults are always sent, so the client type marks them present (maybe null).
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    message: str
    definitions: ToolResult | None = None
    # The last aggregate query: only groups of 10 or more students.
    query: ToolResult | None = None
    # The last query_results call: slices of the published measures.
    results: ToolResult | None = None
    tools_used: list[str]
    # At most three pages to see the answer's numbers on, from links.derive.
    links: list[PageLink] = []
    # Definitions and query results come from the synthetic shared model, never real students.
    source: Literal["synthetic"] = "synthetic"
