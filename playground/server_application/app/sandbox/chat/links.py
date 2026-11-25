"""The "See it on" links under a chat answer, derived from what the answer read.

The server picks the page and every parameter from fixed lists here, never from the model's text,
and sends a page name plus params, never a URL: the client builds the address from its own routes.
A value that isn't on a page's picker list is dropped, so the page opens on its defaults instead.
"""

from collections.abc import Sequence
from typing import get_args

from app.sandbox.aid_momentum.results import MEASURE_LABELS as AID_MEASURE_LABELS
from app.sandbox.aid_momentum.schemas import Measure as AidMeasure
from app.sandbox.course_outcomes.results import GENDER_WORDS, who
from app.sandbox.deaggregation.results import COHORT as POOLED_COHORT
from app.sandbox.deaggregation.results import MEASURES as DEAGGREGATION_MEASURES
from app.sandbox.deaggregation.schemas import Gender, Race
from app.sandbox.executive_view.results import _GAP_MEASURES, _GROUP_LABELS, _KPI_LABELS
from app.sandbox.results.schemas import QuerySpec
from app.sandbox.student_success.equity import DIMENSION_TITLES

from .schemas import KeywordContext, PageLink

MAX_LINKS = 3

RACES = frozenset(get_args(Race))
GENDERS = frozenset(get_args(Gender))
AID_MEASURES = frozenset(get_args(AidMeasure))
COURSE_MEASURES = frozenset({"dfw_rate", "midterm_alert_rate", "midterm_recovery_rate"})
# The minimum enrollment choices the course outcomes picker offers.
MIN_ENROLLMENTS = frozenset({50, 100, 200, 500})
AID_DIMENSIONS = ({"unmet_need_band"}, {"pell"})
DEAGGREGATION_DIMENSIONS = ({"gender", "race"}, {"race"})
# Student success splits no other linked page shows. It is live and shows retention only.
STUDENT_SUCCESS_DIMENSIONS = frozenset({"gender", "age_band"})

COURSE_TITLES = {
    "dfw_rate": "DFW by course",
    "midterm_alert_rate": "Midterm alerts by course",
    "midterm_recovery_rate": "Midterm recovery by course",
}

# The executive view shows gender and Pell groups by these labels; race has none, so it shows the
# stored value, which is the same text as the de-aggregation page's Race choices.
GENDER_BY_LABEL = {
    label: value for value, label in _GROUP_LABELS["gender"].items() if value in GENDERS
}
PELL_LABELS = frozenset(_GROUP_LABELS["pell"].values())
AGE_BAND_LABELS = frozenset(_GROUP_LABELS["age_band"].values())
MEASURE_BY_LABEL = {label: name for name, label in {**_KPI_LABELS, **_GAP_MEASURES}.items()}


def derive(specs: Sequence[QuerySpec], keyword: KeywordContext | None = None) -> list[PageLink]:
    """At most three links, one per page: from the specs in the order they ran, then the keyword."""
    candidates = [_from_spec(spec) for spec in specs]
    if keyword is not None:
        candidates.append(_from_keyword(keyword))
    links: list[PageLink] = []
    for link in candidates:
        if link is None or any(seen.page == link.page for seen in links):
            continue
        links.append(link)
        if len(links) == MAX_LINKS:
            break
    return links


def _from_spec(spec: QuerySpec) -> PageLink | None:
    """The page that shows this spec's slice, or None when no linked page does."""
    # Every linked page reads the pooled cohort, so a single cohort's numbers wouldn't be on it.
    if spec.cohort != POOLED_COHORT:
        return None
    dimensions = set(spec.group_by)
    if "course" in dimensions and spec.measure in COURSE_MEASURES:
        params = _course_race_gender(spec)
        if spec.min_denominator in MIN_ENROLLMENTS:
            params["min_enrollments"] = str(spec.min_denominator)
        return _course_outcomes(spec.measure, params)
    if dimensions in DEAGGREGATION_DIMENSIONS and spec.measure in DEAGGREGATION_MEASURES:
        return _deaggregation(_race_gender(spec.where))
    if dimensions in AID_DIMENSIONS and spec.measure in AID_MEASURES:
        return _aid_momentum(spec.measure)
    if spec.measure == "retention" and len(spec.group_by) == 1:
        [dimension] = spec.group_by
        if dimension in STUDENT_SUCCESS_DIMENSIONS:
            return _student_success(dimension)
    return None


def _from_keyword(keyword: KeywordContext) -> PageLink | None:
    """The page to dig into what was clicked on the executive view, or None."""
    if keyword.kind == "cohort":
        return _student_success(None)
    if keyword.kind != "group" or keyword.group is None:
        return None
    if keyword.group in RACES:
        return _deaggregation({"race": keyword.group})
    if keyword.group in GENDER_BY_LABEL:
        return _deaggregation({"gender": GENDER_BY_LABEL[keyword.group]})
    if keyword.group in PELL_LABELS:
        measure = MEASURE_BY_LABEL.get(keyword.measure or "")
        return _aid_momentum(measure if measure in AID_MEASURES else None)
    if keyword.group in AGE_BAND_LABELS:
        return _student_success("age_band")
    return None


def _race_gender(where: dict[str, str]) -> dict[str, str]:
    """The race and gender a spec filters on, keeping only values the pages' pickers offer."""
    params = {}
    if where.get("race") in RACES:
        params["race"] = where["race"]
    if where.get("gender") in GENDERS:
        params["gender"] = where["gender"]
    return params


def _course_race_gender(spec: QuerySpec) -> dict[str, str]:
    """The race and gender the course outcomes pickers open on for this spec."""
    # A dimension the spec doesn't split by is "all"; a filter value the picker offers is kept.
    params = {}
    if "race" not in spec.group_by:
        params["race"] = "all"
    elif spec.where.get("race") in RACES:
        params["race"] = spec.where["race"]
    if "gender" not in spec.group_by:
        params["gender"] = "all"
    elif spec.where.get("gender") in GENDERS:
        params["gender"] = spec.where["gender"]
    return params


def _who(params: dict[str, str]) -> str:
    """The group in a label, e.g. 'Asian women', or '' when the link sets no group."""
    words = [params.get("race", ""), GENDER_WORDS.get(params.get("gender", ""), "")]
    return " ".join(word for word in words if word)


def _titled(title: str, detail: str) -> str:
    """'Title: detail', or the title alone when there's no detail."""
    return f"{title}: {detail}" if detail else title


def _deaggregation(params: dict[str, str]) -> PageLink:
    """A link to the de-aggregation page for this race and gender."""
    label = _titled("De-aggregation", _who(params))
    return PageLink(page="deaggregation", label=label, params=params)


def _course_outcomes(measure: str, params: dict[str, str]) -> PageLink:
    """A link to the course outcomes page for this race, gender and minimum enrollments."""
    # A left-out picker opens on the page's default, so name a group only when both are set.
    group = ""
    if "race" in params and "gender" in params:
        group = who(params["race"], params["gender"])
    label = _titled(COURSE_TITLES[measure], group)
    return PageLink(page="course-outcomes", label=label, params=params)


def _aid_momentum(measure: str | None) -> PageLink:
    """A link to the aid momentum page, on this measure when one is given."""
    if measure is None:
        return PageLink(page="aid-momentum", label="Unmet need and momentum", params={})
    label = _titled("Unmet need and momentum", AID_MEASURE_LABELS[measure])
    return PageLink(page="aid-momentum", label=label, params={"measure": measure})


def _student_success(dimension: str | None) -> PageLink:
    """A link to student success on its default cohort, split by this dimension if given."""
    if dimension is None:
        return PageLink(page="student-success", label="Student success (live)", params={})
    label = f"Student success (live): retention by {DIMENSION_TITLES[dimension].lower()}"
    return PageLink(page="student-success", label=label, params={"dimension": dimension})
