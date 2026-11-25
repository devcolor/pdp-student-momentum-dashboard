"""Every KPI tile and the chat's query_results give the same value and trend label.

A planted data model with four entering cohorts is published from the real manifest (without the
course and other measures no tile reads, for speed). Each page's tiles are then asked of the
chat's own tool, query_results with include rates and trends, and must match: the value to one
decimal, and the arrow's label, or no label where the tile has no arrow.

Graduation rate is left out on purpose: it comes from the institution's records, not PDP, so it
is never published and the chat can't confirm it. A completion value shown "so far" (a cohort
inside its 3-year window) is published as not_yet_observable, so it can't be confirmed either.
The data is synthetic.
"""

import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from app.sandbox.chat import llm, query_tool, results_tool
from app.sandbox.chat.repo import repo_root
from app.sandbox.executive_view import cohorts
from app.sandbox.results import published
from tests.fake_anthropic import URL, reply, text, tool_use
from tests.published_results import builder, publish_model

YEARS = ["2021-22", "2022-23", "2023-24", "2024-25"]
LENSES = ["all", *YEARS]
# Students per entering cohort. Each year's planted rates differ, so every tile has an arrow.
SIZES = {"2021-22": 100, "2022-23": 110, "2023-24": 104, "2024-25": 121}
# Full academic years each cohort's credits have been seen for, plus the year under way: the two
# oldest have had the 3-year completion window, the two newest haven't.
YEARS_OBSERVED = {"2021-22": 5, "2022-23": 4, "2023-24": 3, "2024-25": 2}
# The measures the tiles read. The rest of the manifest is left out to keep the publish quick.
TILE_MEASURES = {
    "retention",
    "persistence",
    "gateway_math",
    "gateway_english",
    "fall_to_spring_retention",
    "completion",
    "transfer_in_share",
    "part_time_share",
}
# The make-up measure whose everyone denominator is the entering students.
ENTERING = "transfer_in_share"
NOT_PUBLISHED = "Graduation comes from the institution's records, not PDP, so it isn't published."

EXECUTIVE = "/api/v1/sandbox/executive-view/kpis"
STUDENT_SUCCESS = "/api/v1/sandbox/student-success/kpis"
ENROLLMENT = "/api/v1/sandbox/enrollment-trends/kpis"

# Each page's tile id mapped to the published measure behind it; None is the entering count.
EXECUTIVE_TILES = {
    name: name for name in ("retention", "persistence", "gateway_math", "gateway_english")
}
STUDENT_SUCCESS_TILES = {
    "entering_students": None,
    "retention": "retention",
    "fall_to_spring": "fall_to_spring_retention",
    "transfer_out": "persistence",
    "completion": "completion",
}
ENROLLMENT_TILES = {
    "entering_students": None,
    "transfer_share": "transfer_in_share",
    "part_time_share": "part_time_share",
    "fall_to_spring": "fall_to_spring_retention",
}

SCHEMA = """
CREATE TABLE student (
    student_id TEXT, student_age TEXT, race TEXT, ethnicity TEXT, gender TEXT, first_gen TEXT
);
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, cohort_term TEXT, enrollment_type TEXT,
    enrollment_intensity_first_term TEXT, pell_status_first_year TEXT,
    retention BOOLEAN, persistence BOOLEAN,
    completed_gateway_math_year1 TEXT, completed_gateway_english_year1 TEXT,
    gateway_math_status TEXT, gateway_english_status TEXT,
    credit_years_observed INTEGER,
    first_year_to_associates_at_coho INTEGER, first_year_to_certificate_at_coh INTEGER
);
CREATE TABLE term (term_id INTEGER, academic_year TEXT, academic_term TEXT, sort_order INTEGER);
CREATE TABLE student_term_matrix (
    student_id TEXT, term_id INTEGER, retention_fall_to_spring TEXT, academic_standing TEXT,
    educational_goal TEXT, ipeds_grad_rate_status TEXT
);
CREATE TABLE data_provider (
    provider_id INTEGER, source_file TEXT, file_sha256 TEXT, loaded_at TEXT
);
INSERT INTO data_provider VALUES (1, 'test', 'not-a-real-hash', '2026-01-01T00:00:00');
"""


def _planted(year_index: int, i: int, every: int) -> bool:
    """True for about one student in `every`, shifted by year so each year's rate differs."""
    return (i + year_index) % every == 0 or i % (every + year_index + 1) == 0


def _model_rows() -> tuple[list[tuple], list[tuple], list[tuple]]:
    """(students, cohort members, first-fall matrix rows) for every planted cohort."""
    students, members, matrix = [], [], []
    for year_index, year in enumerate(YEARS):
        for i in range(SIZES[year]):
            student_id = f"{year}-{i}"
            students.append(
                (
                    student_id,
                    "20 and younger" if i % 3 else "Older than 24",
                    "Hispanic" if i % 4 == 0 else "White",
                    "N",
                    "F" if i % 2 else "M",
                    None,
                )
            )
            earned = 2 if _planted(year_index, i, 4) else None
            members.append(
                (
                    student_id,
                    year,
                    "FALL",
                    "Transfer-In" if _planted(year_index, i, 3) else "First-Time",
                    "Part-Time" if i % (2 + year_index % 2) == 0 else "Full-Time",
                    "Y" if i % 2 == 0 else "N",
                    not _planted(year_index, i, 2),
                    _planted(year_index, i, 5),
                    "D" if _planted(year_index, i, 3) else "C",
                    "D" if _planted(year_index + 1, i, 4) else "C",
                    "R",
                    "R",
                    YEARS_OBSERVED[year],
                    earned,
                    None,
                )
            )
            matrix.append(
                (
                    student_id,
                    year_index + 1,
                    "not_returning" if _planted(year_index + 2, i, 3) else "still_enrolled",
                    "good_standing",
                    "no_declaration",
                    "completed" if i % 4 == 0 else "dropped_out",
                )
            )
    return students, members, matrix


@pytest.fixture
def model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The planted data model, with every page's live queries pointed at it."""
    path = tmp_path / "model.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.executemany(
        "INSERT INTO term VALUES (?, ?, 'FALL', ?)",
        [(index + 1, year, index) for index, year in enumerate(YEARS)],
    )
    students, members, matrix = _model_rows()
    connection.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?, ?)", students)
    marks = ", ".join(["?"] * len(members[0]))
    connection.executemany(f"INSERT INTO cohort_membership VALUES ({marks})", members)
    connection.executemany("INSERT INTO student_term_matrix VALUES (?, ?, ?, ?, ?, ?)", matrix)
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)
    return path


def _tile_manifest() -> str:
    """The real manifest, with only the measures the tiles read."""
    manifest = yaml.safe_load((repo_root() / "measures" / "manifest.yaml").read_text("utf-8"))
    manifest["measures"] = {
        name: breakdowns
        for name, breakdowns in manifest["measures"].items()
        if name in TILE_MEASURES
    }
    return yaml.safe_dump(manifest, sort_keys=False)


@pytest.fixture
def published_model(
    model: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> builder.ResultsReader:
    """The planted model published by the shared publish step, with the chat's tool reading it."""
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(_tile_manifest(), encoding="utf-8")
    results = publish_model(model, manifest, tmp_path / "success_measures.sqlite")
    reader = builder.ResultsReader(manifest, results)
    monkeypatch.setattr(published, "reader", lambda: reader)
    return reader


def _ask(measure: str, cohort: str) -> dict[str, Any]:
    """The chat tool's answer for a measure's everyone row in one cohort, with its trend."""
    breakdown = published.reader().breakdowns(measure, cohort)[0]
    arguments = {
        "measure": measure,
        "cohort": cohort,
        "group_by": breakdown,
        "include": ["rates", "trends"],
    }
    return results_tool.call(arguments)


def _tiles(client: TestClient, url: str, lens: str | None) -> dict[str, dict[str, Any]]:
    """A page's tiles by id, for one lens or the page's only one."""
    params = {"cohort": lens} if lens else None
    response = client.get(url, params=params)
    assert response.status_code == 200, response.text
    return {item["id"]: item for item in response.json()["items"]}


def _label(tile: dict[str, Any]) -> str | None:
    """The tile's arrow label, or None when it has no arrow."""
    return tile["trend"]["label"] if tile["trend"] else None


def _check_entering(tile: dict[str, Any], cohort: str) -> None:
    """An entering students tile against the make-up measure's everyone denominator and trend."""
    answer = _ask(ENTERING, cohort)
    assert answer["everyone"]["denominator"] == tile["value"], cohort
    trend = answer["entering_students_trend"]
    assert (trend["label"] if trend else None) == _label(tile), cohort


def _check_rate(tile: dict[str, Any], measure: str, cohort: str) -> None:
    """A percent tile against the measure's published everyone row and its trend."""
    everyone = _ask(measure, cohort)["everyone"]
    assert everyone["status"] == "ok", (measure, cohort)
    assert round(everyone["metric_rate"] * 100, 1) == tile["value"], (measure, cohort)
    assert everyone["trend_label"] == _label(tile), (measure, cohort)


def _check_page(tiles: dict[str, dict[str, Any]], mapping: dict, cohort: str) -> list[str]:
    """Check every mapped tile on a page for one published cohort; returns the ids checked."""
    checked = []
    for tile_id, measure in mapping.items():
        tile = tiles.get(tile_id)
        if tile is None:
            continue
        if measure is None:
            _check_entering(tile, cohort)
        else:
            _check_rate(tile, measure, cohort)
        checked.append(tile_id)
    return checked


@pytest.mark.parametrize("lens", LENSES)
def test_executive_view_tiles_match_the_chat(
    client: TestClient, published_model: builder.ResultsReader, lens: str
) -> None:
    """Every executive view tile but graduation, for each lens."""
    tiles = _tiles(client, EXECUTIVE, lens)
    checked = _check_page(tiles, EXECUTIVE_TILES, cohorts.published_cohort(lens))

    assert checked == list(EXECUTIVE_TILES)
    assert "graduation" in tiles, NOT_PUBLISHED  # shown, but nothing published to check it with
    if lens == cohorts.PARTLY_OBSERVED:
        assert tiles["retention"]["trend"] is None and tiles["persistence"]["trend"] is None


@pytest.mark.parametrize("lens", LENSES)
def test_student_success_tiles_match_the_chat(
    client: TestClient, published_model: builder.ResultsReader, lens: str
) -> None:
    """Every student success snapshot tile, for each lens; the presidential cards are these."""
    tiles = _tiles(client, STUDENT_SUCCESS, lens)
    mapping = dict(STUDENT_SUCCESS_TILES)
    completion = tiles.get("completion")
    if completion is not None and (
        lens == "all" or completion["detail"].endswith("isn't over yet")
    ):
        # Checked below: the published pool, or this year, isn't observable yet.
        mapping.pop("completion")
    checked = _check_page(tiles, mapping, cohorts.published_cohort(lens))

    assert checked == list(mapping)
    assert completion is not None
    if lens == "all":
        _check_pooled_completion(completion)
    elif completion["detail"].endswith("isn't over yet"):
        # A count so far: the published row is not observable, so the chat can't confirm it.
        assert _ask("completion", lens)["everyone"]["status"] == "not_yet_observable"
        assert completion["trend"] is None


def _check_pooled_completion(tile: dict[str, Any]) -> None:
    """All cohorts' completion pools only the observed years: the sum of their published rows.

    The published pool holds a year short of the window, so it is not_yet_observable.
    """
    assert _ask("completion", cohorts.POOL)["everyone"]["status"] == "not_yet_observable"
    years = [year for year in cohorts.POOL_YEARS if YEARS_OBSERVED[year] - 1 >= 3]
    assert tile["detail"].endswith(f"(cohorts {', '.join(years)} only)")
    rows = [_ask("completion", year)["everyone"] for year in years]
    numerator = sum(int(row["numerator"]) for row in rows)
    denominator = sum(int(row["denominator"]) for row in rows)
    assert tile["detail"].startswith(f"{numerator:,} of {denominator:,} ")
    assert round(round(numerator / denominator, 4) * 100, 1) == tile["value"]
    assert tile["trend"] is None


def test_enrollment_trends_tiles_match_the_chat(
    client: TestClient, published_model: builder.ResultsReader
) -> None:
    """Every enrollment trends tile, for the latest entering cohort it shows."""
    response = client.get(ENROLLMENT).json()
    latest = YEARS[-1]
    assert response["meta"]["filters"][0] == f"{latest} cohort"
    tiles = {item["id"]: item for item in response["items"]}

    assert _check_page(tiles, ENROLLMENT_TILES, latest) == list(ENROLLMENT_TILES)
    assert all(tile["trend"] is not None for tile in tiles.values())


def test_the_year_2_rule_is_the_manifests_no_trend() -> None:
    """The tiles' no-arrow rule for a cohort short of year 2 and the published no_trend agree."""
    manifest = yaml.safe_load((repo_root() / "measures" / "manifest.yaml").read_text("utf-8"))
    no_trend = manifest["single_cohorts"]["no_trend"]
    assert set(no_trend) == set(cohorts.NEEDS_YEAR_2)
    assert all(years == [cohorts.PARTLY_OBSERVED] for years in no_trend.values())
    assert manifest["single_cohorts"]["years"] == cohorts.SINGLE_YEARS


def test_the_chat_is_told_to_quote_the_published_trend(
    client: TestClient, published_model: builder.ResultsReader, use_fake
) -> None:
    """Asked how a tile changed, the model gets the trend rule and the published trend_label."""
    arguments = {
        "measure": "retention",
        "cohort": "2023-24",
        "group_by": ["gender"],
        "include": ["rates", "trends"],
    }
    fake = use_fake(
        reply(tool_use(results_tool.NAME, arguments)),
        reply(text("Retention changed as the tile says. The data is synthetic.")),
    )
    response = client.post(URL, json={"prompt": "What is retention and how did it change?"})

    assert response.status_code == 200, response.text
    [system] = fake.requests[0]["system"]
    assert 'include\n   ["rates", "trends"] and quote trend_label as given' in system["text"]
    assert "trend_label" in llm.CHAT_RULES
    tiles = _tiles(client, EXECUTIVE, "2023-24")
    # The tool result the model read holds the tile's own label.
    assert tiles["retention"]["trend"]["label"] in str(fake.requests[1]["messages"])
