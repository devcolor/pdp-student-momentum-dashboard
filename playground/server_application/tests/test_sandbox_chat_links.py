"""The "See it on" links under a chat answer: which page, which params, and what is dropped."""

from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from app.sandbox.chat import links
from app.sandbox.chat.schemas import KeywordContext, LinkedPage, PageLink, SuggestResponse
from app.sandbox.results.schemas import QuerySpec
from tests.fake_anthropic import URL, reply, text, tool_use
from tests.published_results import COHORT

BLACK = "Black or African American"


def spec(measure: str, group_by: list[str], **fields: Any) -> QuerySpec:
    """A spec on the pooled cohort the pages read."""
    return QuerySpec(measure=measure, cohort=COHORT, group_by=group_by, **fields)


def keyword(kind: str, **names: str) -> KeywordContext:
    """An executive view keyword; its names are checked as they are on a real request."""
    return KeywordContext(kind=kind, **names)


def only(found: list[PageLink]) -> PageLink:
    """The single link derived, failing if there are none or several."""
    [link] = found
    return link


# Rule a: a course breakdown of a course measure opens course outcomes.


def test_a_dfw_by_course_spec_links_to_course_outcomes_with_its_group() -> None:
    link = only(
        links.derive(
            [
                spec(
                    "dfw_rate",
                    ["course", "gender", "race"],
                    where={"gender": "F", "race": BLACK},
                    min_denominator=200,
                )
            ]
        )
    )

    assert link.page == "course-outcomes"
    assert link.params == {"race": BLACK, "gender": "F", "min_enrollments": "200"}
    assert link.label == "DFW by course: Black or African American women"


@pytest.mark.parametrize(
    ("measure", "label"),
    [
        ("midterm_alert_rate", "Midterm alerts by course: Everyone"),
        ("midterm_recovery_rate", "Midterm recovery by course: Everyone"),
    ],
)
def test_midterm_measures_by_course_link_to_course_outcomes(measure: str, label: str) -> None:
    link = only(links.derive([spec(measure, ["course"])]))

    assert link.page == "course-outcomes"
    assert link.params == {"race": "all", "gender": "all"}
    assert link.label == label


@pytest.mark.parametrize(
    ("group_by", "where", "params", "label"),
    [
        (
            ["course", "gender", "race"],
            {"gender": "M", "race": BLACK},
            {"race": BLACK, "gender": "M"},
            "DFW by course: Black or African American men",
        ),
        (
            ["course", "race"],
            {"race": BLACK},
            {"race": BLACK, "gender": "all"},
            "DFW by course: Black or African American students",
        ),
        (
            ["course", "gender"],
            {"gender": "F"},
            {"race": "all", "gender": "F"},
            "DFW by course: Women",
        ),
        (["course"], {}, {"race": "all", "gender": "all"}, "DFW by course: Everyone"),
    ],
)
def test_a_dimension_the_spec_does_not_split_by_opens_as_all(
    group_by: list[str], where: dict[str, str], params: dict[str, str], label: str
) -> None:
    link = only(links.derive([spec("dfw_rate", group_by, where=where)]))

    assert (link.page, link.params, link.label) == ("course-outcomes", params, label)


@pytest.mark.parametrize(
    ("group_by", "where", "params"),
    [
        # Race is split by but not filtered, so the page opens on its default race.
        (["course", "gender", "race"], {"gender": "M"}, {"gender": "M"}),
        (["course", "race"], {"race": "Nope"}, {"gender": "all"}),
        (["course", "gender"], {"gender": "X"}, {"race": "all"}),
    ],
)
def test_a_course_race_or_gender_the_pickers_do_not_offer_is_left_out(
    group_by: list[str], where: dict[str, str], params: dict[str, str]
) -> None:
    link = only(links.derive([spec("dfw_rate", group_by, where=where)]))

    # A left-out picker opens on the page's default, so the label names no group.
    assert (link.params, link.label) == (params, "DFW by course")


def test_a_min_denominator_the_picker_does_not_offer_is_dropped() -> None:
    link = only(links.derive([spec("dfw_rate", ["course"], min_denominator=137)]))

    assert link.page == "course-outcomes"
    assert "min_enrollments" not in link.params


def test_a_course_breakdown_of_another_measure_is_not_course_outcomes() -> None:
    assert links.derive([spec("retention", ["course"])]) == []


# Rule b: a race, or race by gender, breakdown opens de-aggregation.


def test_a_race_by_gender_spec_links_to_deaggregation_with_its_group() -> None:
    found = links.derive(
        [spec("gateway_math", ["gender", "race"], where={"race": "Asian", "gender": "M"})]
    )

    link = only(found)
    assert link.page == "deaggregation"
    assert link.params == {"race": "Asian", "gender": "M"}
    assert link.label == "De-aggregation: Asian men"


def test_a_race_spec_without_a_filter_links_to_deaggregation_on_its_defaults() -> None:
    link = only(links.derive([spec("retention", ["race"])]))

    assert (link.page, link.params, link.label) == ("deaggregation", {}, "De-aggregation")


def test_a_race_or_gender_the_pickers_do_not_offer_is_dropped() -> None:
    found = links.derive(
        [spec("retention", ["gender", "race"], where={"race": "Nope", "gender": "X"})]
    )

    assert only(found).params == {}


def test_a_measure_the_deaggregation_page_does_not_show_is_not_linked() -> None:
    assert links.derive([spec("midterm_recovery_rate", ["gender", "race"])]) == []


def test_a_gender_only_breakdown_is_not_deaggregation() -> None:
    assert links.derive([spec("persistence", ["gender"])]) == []


# Rule c: a Pell or unmet need breakdown of an aid measure opens aid momentum.


@pytest.mark.parametrize("dimension", ["unmet_need_band", "pell"])
def test_an_aid_breakdown_links_to_aid_momentum_on_its_measure(dimension: str) -> None:
    link = only(links.derive([spec("credit_completion", [dimension])]))

    assert link.page == "aid-momentum"
    assert link.params == {"measure": "credit_completion"}
    assert link.label == "Unmet need and momentum: Credit completion"


def test_an_aid_breakdown_of_an_unknown_measure_is_not_linked() -> None:
    assert links.derive([spec("midterm_alert_rate", ["unmet_need_band"])]) == []


def test_an_aid_breakdown_with_another_dimension_is_not_linked() -> None:
    assert links.derive([spec("retention", ["pell", "race"])]) == []


# Rule d: a retention breakdown by gender or age group opens student success on that split.


@pytest.mark.parametrize(
    ("dimension", "label"),
    [
        ("gender", "Student success (live): retention by gender"),
        ("age_band", "Student success (live): retention by age group"),
    ],
)
def test_retention_by_gender_or_age_links_to_student_success_on_that_split(
    dimension: str, label: str
) -> None:
    link = only(links.derive([spec("retention", [dimension])]))

    assert (link.page, link.params, link.label) == (
        "student-success",
        {"dimension": dimension},
        label,
    )


@pytest.mark.parametrize("dimension", ["gender", "age_band"])
def test_another_measure_by_gender_or_age_is_not_student_success(dimension: str) -> None:
    assert links.derive([spec("persistence", [dimension])]) == []
    assert links.derive([spec("gateway_math", [dimension])]) == []


@pytest.mark.parametrize("dimension", ["enrollment_intensity", "affinity", "educational_goal"])
def test_retention_by_a_split_student_success_does_not_offer_is_not_linked(
    dimension: str,
) -> None:
    assert links.derive([spec("retention", [dimension])]) == []


def test_retention_by_age_and_another_dimension_is_not_linked() -> None:
    assert links.derive([spec("retention", ["age_band", "gender"])]) == []


def test_retention_by_race_and_pell_keep_their_own_pages() -> None:
    assert only(links.derive([spec("retention", ["race"])])).page == "deaggregation"
    assert only(links.derive([spec("retention", ["pell"])])).page == "aid-momentum"


@pytest.mark.parametrize("group_by", [["race"], ["pell"], ["gender"]])
def test_a_single_cohort_spec_is_not_linked(group_by: list[str]) -> None:
    # Every linked page reads the pooled cohort, so it wouldn't show a single cohort's numbers.
    single = QuerySpec(measure="retention", cohort="2022-23", group_by=group_by)
    assert links.derive([single]) == []


def test_a_single_cohort_spec_falls_back_to_the_keyword() -> None:
    single = QuerySpec(measure="gateway_math", cohort="2022-23", group_by=["race"])
    link = only(links.derive([single], keyword("group", measure="Retention", group=BLACK)))
    assert link.page == "deaggregation"
    assert link.params == {"race": BLACK}


# Rule e: with no spec that matches, the executive view keyword picks the page.


def test_a_race_group_keyword_links_to_deaggregation_for_that_race() -> None:
    link = only(links.derive([], keyword("group", measure="Retention", group=BLACK)))

    assert link.page == "deaggregation"
    assert link.params == {"race": BLACK}


@pytest.mark.parametrize(("label", "value"), [("Male students", "M"), ("Female students", "F")])
def test_a_gender_group_keyword_links_to_deaggregation_for_that_gender(
    label: str, value: str
) -> None:
    link = only(links.derive([], keyword("group", measure="Gateway math", group=label)))

    assert (link.page, link.params) == ("deaggregation", {"gender": value})


@pytest.mark.parametrize(
    ("label", "measure"),
    [
        ("Retention", "retention"),
        ("Persistence elsewhere", "persistence"),
        ("Gateway math", "gateway_math"),
        ("Gateway English", "gateway_english"),
    ],
)
@pytest.mark.parametrize("group", ["Pell recipients", "Students without Pell"])
def test_a_pell_group_keyword_links_to_aid_momentum_on_its_measure(
    label: str, measure: str, group: str
) -> None:
    link = only(links.derive([], keyword("group", measure=label, group=group)))

    assert (link.page, link.params) == ("aid-momentum", {"measure": measure})


def test_a_cohort_keyword_links_to_student_success_without_params() -> None:
    link = only(links.derive([], keyword("cohort", cohort="2024-25")))

    assert (link.page, link.params, link.label) == ("student-success", {}, "Student success (live)")


@pytest.mark.parametrize("group", ["Age 20 and younger", "Age over 20, up to 24", "Age over 24"])
def test_an_age_group_keyword_links_to_student_success_split_by_age(group: str) -> None:
    link = only(links.derive([], keyword("group", measure="Retention", group=group)))

    assert (link.page, link.params) == ("student-success", {"dimension": "age_band"})
    assert link.label == "Student success (live): retention by age group"


@pytest.mark.parametrize(
    "clicked",
    [
        keyword("measure", measure="Retention"),
        keyword("group", measure="Retention", group="Part-time students"),
        # UNKNOWN is a stored race value, but not one the de-aggregation picker offers.
        keyword("group", measure="Retention", group="UNKNOWN"),
    ],
)
def test_a_keyword_with_no_page_of_its_own_gives_no_link(clicked: KeywordContext) -> None:
    assert links.derive([], clicked) == []


# Order, dedupe and the cap.


def test_specs_come_before_the_keyword_and_one_page_is_linked_once() -> None:
    found = links.derive(
        [
            spec("retention", ["gender", "race"], where={"race": "Asian"}),
            spec("gateway_math", ["race"]),
        ],
        keyword("group", measure="Retention", group=BLACK),
    )

    link = only(found)
    assert link.params == {"race": "Asian"}


def test_at_most_three_links_are_returned_and_the_fourth_page_is_dropped() -> None:
    found = links.derive(
        [
            spec("dfw_rate", ["course"]),
            spec("retention", ["race"]),
            spec("retention", ["pell"]),
            spec("retention", ["age_band"]),
        ],
        keyword("cohort", cohort="2024-25"),
    )

    assert [link.page for link in found] == ["course-outcomes", "deaggregation", "aid-momentum"]


def test_three_pages_with_repeats_give_one_link_each_and_the_keyword_comes_last() -> None:
    found = links.derive(
        [
            spec("retention", ["race"], where={"race": "Asian"}),
            spec("gateway_math", ["race"]),
            spec("retention", ["gender"]),
            spec("retention", ["age_band"]),
        ],
        keyword("group", measure="Retention", group="Pell recipients"),
    )

    assert [(link.page, link.params) for link in found] == [
        ("deaggregation", {"race": "Asian"}),
        ("student-success", {"dimension": "gender"}),
        ("aid-momentum", {"measure": "retention"}),
    ]


def test_every_param_a_link_sends_is_on_an_allow_list() -> None:
    found = links.derive(
        [
            spec(
                "dfw_rate",
                ["course", "gender", "race"],
                where={"race": BLACK, "gender": "Q"},
                min_denominator=7,
            ),
            spec("retention", ["age_band"]),
            spec("persistence", ["unmet_need_band"]),
        ]
    )

    assert [link.params for link in found] == [
        {"race": BLACK},
        {"dimension": "age_band"},
        {"measure": "persistence"},
    ]


def test_nothing_matching_gives_no_links() -> None:
    assert links.derive([spec("retention", ["enrollment_intensity"])]) == []
    assert links.derive([]) == []


def test_every_page_a_link_can_name_is_one_the_client_knows() -> None:
    assert set(get_args(LinkedPage)) == {
        "deaggregation",
        "course-outcomes",
        "aid-momentum",
        "student-success",
    }
    with pytest.raises(ValueError):
        PageLink(page="executive-view", label="Executive view", params={})


def test_links_are_always_sent_even_when_empty() -> None:
    assert "links" in SuggestResponse.model_json_schema(mode="serialization")["required"]


# Through the chat route: every successful query_results call counts, failures don't.


def test_the_answer_links_every_answered_spec_and_skips_a_refused_one(
    client: TestClient, use_fake, published_results: Path
) -> None:
    by_race = {"measure": "gateway_math", "cohort": COHORT, "group_by": ["race"]}
    refused = {"measure": "gateway_math", "cohort": COHORT, "group_by": ["pell"]}
    by_group = {
        "measure": "gateway_math",
        "cohort": COHORT,
        "group_by": ["race", "gender"],
        "where": {"race": BLACK, "gender": "M"},
    }
    use_fake(
        reply(tool_use("query_results", by_group, "toolu_1")),
        reply(tool_use("query_results", refused, "toolu_2")),
        reply(tool_use("query_results", by_race, "toolu_3")),
        reply(text("Black or African American men pass gateway math at 14.7%.")),
    )

    body = client.post(URL, json={"prompt": "How do Black men do in gateway math?"}).json()

    # The first spec gave the link even though results holds the last call.
    assert body["results"]["input"] == by_race
    assert body["links"] == [
        {
            "page": "deaggregation",
            "label": "De-aggregation: Black or African American men",
            "params": {"race": BLACK, "gender": "M"},
        }
    ]


def test_a_refused_spec_alone_gives_no_link(
    client: TestClient, use_fake, published_results: Path
) -> None:
    refused = {"measure": "gateway_math", "cohort": COHORT, "group_by": ["pell"]}
    use_fake(
        reply(tool_use("query_results", refused)),
        reply(text("That breakdown isn't published.")),
    )

    body = client.post(URL, json={"prompt": "Gateway math by Pell?"}).json()

    assert body["results"]["is_error"] is True
    assert body["links"] == []


def test_a_cohort_keyword_links_through_the_route(client: TestClient, use_fake) -> None:
    use_fake(reply(text("The 2024-25 cohort is still in its first year.")))

    body = client.post(
        URL,
        json={"prompt": "Tell me about it", "context": {"kind": "cohort", "cohort": "2024-25"}},
    ).json()

    assert body["links"] == [
        {"page": "student-success", "label": "Student success (live)", "params": {}}
    ]


def test_an_answer_without_tools_sends_an_empty_links_list(client: TestClient, use_fake) -> None:
    use_fake(reply(text("Hello.")))

    body = client.post(URL, json={"prompt": "hi"}).json()

    assert body["links"] == []
