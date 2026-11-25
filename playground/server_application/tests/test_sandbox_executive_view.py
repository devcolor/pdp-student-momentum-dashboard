"""Known-answer tests for the executive view.

The planted model is published with the shared publish step (measures/publish.py), so the tiles and
the gaps card read the same numbers the live measures give, through the query builder.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.sandbox.chat import query_tool
from app.sandbox.enrollment_trends.schemas import TermResponse, TermRow
from app.sandbox.executive_view import cohorts, results
from app.sandbox.results import published
from app.sandbox.shared import ChartMeta
from tests.published_results import EXEC_MANIFEST, builder, gap, publish_model, row
from tests.test_sandbox_executive_view_small_counts import lone_lines

KPIS = "/api/v1/sandbox/executive-view/kpis"
GAPS = "/api/v1/sandbox/executive-view/gaps"
HEADCOUNT = "/api/v1/sandbox/executive-view/headcount"

SCHEMA = """
CREATE TABLE student (
    student_id TEXT, student_age TEXT, race TEXT, ethnicity TEXT, gender TEXT, first_gen TEXT
);
CREATE TABLE cohort_membership (
    student_id TEXT, cohort TEXT, cohort_term TEXT, enrollment_type TEXT,
    enrollment_intensity_first_term TEXT, pell_status_first_year TEXT,
    retention BOOLEAN, persistence BOOLEAN,
    completed_gateway_math_year1 TEXT, completed_gateway_english_year1 TEXT,
    gateway_math_status TEXT, gateway_english_status TEXT
);
CREATE TABLE term (term_id INTEGER, academic_year TEXT, academic_term TEXT);
INSERT INTO term VALUES (1, '2021-22', 'FALL'), (2, '2022-23', 'FALL'), (3, '2023-24', 'FALL');
CREATE TABLE student_term_matrix (student_id TEXT, term_id INTEGER, ipeds_grad_rate_status TEXT);
CREATE TABLE data_provider (
    provider_id INTEGER, source_file TEXT, file_sha256 TEXT, loaded_at TEXT
);
INSERT INTO data_provider VALUES (1, 'test', 'not-a-real-hash', '2026-01-01T00:00:00');
"""

COHORTS = ["2021-22", "2022-23", "2023-24"]
POOL = "2021-22 + 2022-23 + 2023-24"
REPO = Path(__file__).resolve().parents[3]
KPI_MEASURES = ["retention", "persistence", "gateway_math", "gateway_english"]


def _is_retained(i: int) -> bool:
    """Part-time students 0-99 retain 40 of 100; full-time students 100-199 retain 80 of 100."""
    return i < 40 or 100 <= i < 180


def _race(i: int) -> str:
    """Hispanic students are 12 of 21 retained, a small gap that should read as noise."""
    return "Hispanic" if i % 10 == 0 or i == 41 else "White"


def _gateway_flag(i: int) -> str:
    """Half complete, spread evenly across the planted groups so no gateway gap appears."""
    return "C" if i % 4 in (1, 2) else "D"


def _student_rows() -> tuple[list[tuple], list[tuple]]:
    """200 students with planted retention, persistence and gateway outcomes."""
    students = []
    members = []
    for i in range(200):
        student_id = f"s{i}"
        students.append((student_id, "Older than 24", _race(i), "N", "F", None))
        members.append(
            (
                student_id,
                COHORTS[i % 3],
                "FALL",
                "First-time",
                "Part-time" if i < 100 else "Full-time",
                "Y",
                _is_retained(i),
                i % 10 == 0,
                _gateway_flag(i),
                _gateway_flag(i),
                "R",
                "R",
            )
        )
    return students, members


@pytest.fixture
def model_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the read-only backend at a small data model with planted gaps."""
    path = tmp_path / "model.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    students, members = _student_rows()
    connection.executemany("INSERT INTO student VALUES (?, ?, ?, ?, ?, ?)", students)
    connection.executemany(
        "INSERT INTO cohort_membership VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", members
    )
    # Every student's first fall has an IPEDS status; every 4th graduated: 50 of 200.
    connection.executemany(
        "INSERT INTO student_term_matrix VALUES (?, ?, ?)",
        [(f"s{i}", i % 3 + 1, "completed" if i % 4 == 0 else "dropped_out") for i in range(200)],
    )
    connection.commit()
    connection.close()

    db, _, config = query_tool._mcp()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=path))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)


@pytest.fixture
def published_model(
    model_db: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> builder.ResultsReader:
    """The planted model published from the executive view's manifest, with the builder on it."""
    manifest = tmp_path / "exec_manifest.yaml"
    manifest.write_text(EXEC_MANIFEST, encoding="utf-8")
    results_file = publish_model(tmp_path / "model.db", manifest, tmp_path / "exec.sqlite")
    reader = builder.ResultsReader(manifest, results_file)
    monkeypatch.setattr(published, "reader", lambda: reader)
    return reader


def test_all_cohorts_is_the_published_pool() -> None:
    """The pooled lens is the manifest's pool, so 2024-25, not fully observed, stays out of it."""
    assert results._years_for("all") == ["2021-22", "2022-23", "2023-24"]
    assert results._cohort_filters("all") == ["Cohorts 2021-22 to 2023-24, pooled"]
    assert results._cohort_filters("2024-25") == ["2024-25 cohort", "Only partly observed so far"]
    assert cohorts.published_cohort("all") == "2021-22 + 2022-23 + 2023-24"
    assert cohorts.published_cohort("2022-23") == "2022-23"


def test_the_older_cohort_names_still_read_the_same() -> None:
    """The student success pages and the chat import these from results."""
    assert results._COHORT_YEARS == ["2021-22", "2022-23", "2023-24", "2024-25"]
    assert results._PARTLY_OBSERVED == "2024-25"
    assert results._previous_year("2023-24") == "2022-23"
    assert results._previous_year("2021-22") is None
    assert results._previous_year("all") is None


@pytest.mark.usefixtures("published_model")
def test_kpis_return_each_measure_for_everyone(client: TestClient) -> None:
    body = client.get(KPIS, params={"cohort": "all"}).json()

    assert body["meta"]["source"] == "synthetic"
    assert [(item["id"], item["value"]) for item in body["items"]] == [
        ("retention", 60.0),
        ("persistence", 10.0),
        ("gateway_math", 50.0),
        ("gateway_english", 50.0),
        ("graduation", 25.0),
    ]
    assert body["items"][0]["detail"].startswith("120 of 200 students")
    assert body["items"][4]["detail"].startswith("50 of 200 first-time full-time students")
    assert [item["trend"] for item in body["items"]] == [None, None, None, None, None]


@pytest.mark.usefixtures("published_model")
def test_kpis_for_one_cohort_compare_with_the_cohort_before_it(client: TestClient) -> None:
    body = client.get(KPIS, params={"cohort": "2023-24"}).json()

    assert body["meta"]["filters"][0] == "2023-24 cohort"
    assert body["items"][0]["value"] == 60.6
    assert body["items"][0]["trend"] == {
        "direction": "up",
        "status": "good",
        "label": "+1.5% vs 2022-23",
    }
    assert body["items"][1]["trend"] == {
        "direction": "down",
        "status": "bad",
        "label": "−13.0% vs 2022-23",
    }


@pytest.mark.usefixtures("published_model")
def test_kpis_for_the_oldest_cohort_have_no_trend(client: TestClient) -> None:
    body = client.get(KPIS, params={"cohort": "2021-22"}).json()

    assert [item["trend"] for item in body["items"]] == [None, None, None, None, None]


def test_kpis_reject_an_unknown_cohort(client: TestClient) -> None:
    assert client.get(KPIS, params={"cohort": "1999-00"}).status_code == 422


@pytest.mark.parametrize(
    ("measure", "previous", "latest", "direction", "status", "label"),
    [
        ("retention", 0.50, 0.55, "up", "good", "+10.0% vs 2022-23"),
        ("retention", 0.55, 0.50, "down", "bad", "−9.1% vs 2022-23"),
        ("retention", 0.50, 0.505, "up", "good", "+1.0% vs 2022-23"),
        ("retention", 0.50, 0.4975, "flat", "neutral", "−0.5% vs 2022-23"),
        ("persistence", 0.10, 0.20, "up", "good", "+100.0% vs 2022-23"),
    ],
)
def test_trend_reads_direction_and_status(
    measure: str, previous: float, latest: float, direction: str, status: str, label: str
) -> None:
    trend = results._trend(measure, previous, latest, "2022-23")

    assert trend is not None
    assert (trend.direction, trend.status, trend.label) == (direction, status, label)


def test_trend_uses_the_shared_band_and_names_it() -> None:
    assert results._trend("graduation", 0.50, 0.504, "2022-23").direction == "flat"
    assert results._same_band_filter() == "Under 1% is the same"


def test_trend_is_missing_when_a_cohort_has_no_rate() -> None:
    assert results._trend("retention", None, 0.5, "2022-23") is None
    assert results._trend("retention", 0.0, 0.5, "2022-23") is None


@pytest.mark.usefixtures("published_model")
def test_gaps_follow_the_selected_cohort(client: TestClient) -> None:
    body = client.get(GAPS, params={"cohort": "2023-24"}).json()

    assert body["meta"]["filters"] == ["2023-24 cohort"]
    assert body["rows"][0]["group"] == "Part-time students"
    assert body["rows"][0]["n"] == 33
    assert body["rows"][0]["rate"] == 39.4
    assert body["rows"][0]["by_cohort"] is None


@pytest.mark.usefixtures("published_model")
def test_gaps_show_only_real_shortfalls(client: TestClient) -> None:
    body = client.get(GAPS, params={"cohort": "all"}).json()

    assert body["meta"]["source"] == "synthetic"
    # Full-time is ahead, Hispanic is noise, and the gateway rates are equal across groups.
    assert body["rows"] == [
        {
            "measure": "Retention",
            "group": "Part-time students",
            "rate": 40.0,
            "gap_pts": -40.0,
            "n": 100,
            "students_behind": 40,
            "by_cohort": [
                {"cohort": "2021-22", "students_behind": 13},
                {"cohort": "2022-23", "students_behind": 13},
                {"cohort": "2023-24", "students_behind": 14},
            ],
        }
    ]
    assert body["meta"]["takeaway"] == (
        "Largest gap: Part-time students on Retention, 40.0 points below everyone else, "
        "worth about 40 students."
    )


def test_headcount_rewords_the_shared_chart_and_keeps_its_rows(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [TermRow(term="Fall 21", cohort="2021-22", n=30, term_total=30)]
    meta = ChartMeta(title="Old", description="Kept", takeaway="Old", fields_used=[])
    shared = TermResponse(meta=meta, rows=rows)
    monkeypatch.setattr(results.enrollment_results, "get_by_term", lambda: shared)

    body = client.get(HEADCOUNT).json()

    assert body["meta"]["title"] == "Headcount by terms since entry"
    assert body["meta"]["description"] == "Kept"
    assert body["meta"]["takeaway"].startswith("Each line follows one entering cohort")
    assert body["rows"] == [{"term": "Fall 21", "cohort": "2021-22", "n": 30, "term_total": 30}]


@pytest.mark.usefixtures("published_model")
def test_kpis_explain_a_model_that_is_not_loaded(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The graduation tile is still counted live, so a missing model is still a clear 503."""
    db, _, config = query_tool._mcp()
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    backend = db.backend_for(config.Settings(backend="sqlite", sqlite_path=empty))
    monkeypatch.setattr(query_tool, "backend", lambda: backend)

    response = client.get(KPIS, params={"cohort": "2023-24"})

    assert response.status_code == 503
    assert "Load it from the Sandbox pipeline page" in response.text


@pytest.mark.usefixtures("published_model")
def test_kpis_follow_the_page_filters(client: TestClient) -> None:
    """With Race: Hispanic on, retention counts only the 21 Hispanic students, 12 retained."""
    response = client.get(KPIS, params={"cohort": "all", "race": "hispanic"})

    assert response.status_code == 200
    retention = next(item for item in response.json()["items"] if item["id"] == "retention")
    assert retention["value"] == 57.1
    assert retention["detail"].startswith("12 of 21 students")
    assert "Race: Hispanic" in response.json()["meta"]["filters"]


@pytest.mark.usefixtures("published_model")
def test_filtered_kpis_count_like_the_shared_measures(client: TestClient) -> None:
    """Every student is over 24, so that filter matches everyone and must give the same numbers."""
    shared = client.get(KPIS, params={"cohort": "all"}).json()["items"]
    filtered = client.get(KPIS, params={"cohort": "all", "age": "over_24"}).json()["items"]

    def numbers(items: list[dict]) -> list[tuple]:
        return [(item["id"], item["value"], item["detail"]) for item in items]

    assert numbers(filtered) == numbers(shared)


@pytest.mark.usefixtures("published_model")
def test_kpis_reject_an_unknown_filter_value(client: TestClient) -> None:
    """A filter value outside the menu is a 422, never written into a query."""
    assert client.get(KPIS, params={"race": "martian"}).status_code == 422


HOME_STATES = "/api/v1/sandbox/executive-view/home-states"


@pytest.mark.usefixtures("model_db")
def test_home_states_count_students_and_hide_small_states(
    client: TestClient, tmp_path: Path
) -> None:
    """150 IL, 45 IN, 5 WI: WI is under 10 and alone, so IN, the smaller shown state, covers it."""
    connection = sqlite3.connect(tmp_path / "model.db")
    connection.execute(
        "CREATE TABLE student_attribute (student_id TEXT, attribute_key TEXT, attribute_value TEXT)"
    )
    states = ["IL"] * 150 + ["IN"] * 45 + ["WI"] * 5
    connection.executemany(
        "INSERT INTO student_attribute VALUES (?, 'home_state', ?)",
        [(f"s{i}", state) for i, state in enumerate(states)],
    )
    connection.commit()
    connection.close()

    body = client.get(HOME_STATES, params={"cohort": "all"}).json()

    assert body["rows"] == [
        {"state": "IL", "n": 150, "share": 75.0},
        {"state": "IN", "n": None, "share": None},
        {"state": "WI", "n": None, "share": None},
    ]
    assert body["meta"]["source"] == "synthetic"
    # A total beside the shown states would give away the hidden ones.
    assert body["meta"]["takeaway"] == "75.0% of these students are from Illinois."

    hispanic = client.get(HOME_STATES, params={"cohort": "all", "race": "hispanic"}).json()
    assert sum(row["n"] or 0 for row in hispanic["rows"]) <= 21


def _home_state(i: int) -> str:
    """NY is 13, 8 and 10 in the planted cohorts, IN 20 in each, and the rest IL.

    Students alternate cohorts (cohort i % 3), so i // 3 is a student's place in its cohort.
    """
    place = i // 3
    new_yorkers = [13, 8, 10][i % 3]
    if place < new_yorkers:
        return "NY"
    return "IN" if place < new_yorkers + 20 else "IL"


@pytest.mark.usefixtures("model_db")
def test_home_states_hide_across_the_pool_and_its_years(client: TestClient, tmp_path: Path) -> None:
    """NY's 8 in 2022-23 is hidden there, but the pooled 31 minus 13 and 10 would give it back.

    So no lens leaves a state the only one hidden in its year, or in the state's line across the
    pool and its years. The pool keeps every state; each year shows only IL.
    """
    connection = sqlite3.connect(tmp_path / "model.db")
    connection.execute(
        "CREATE TABLE student_attribute (student_id TEXT, attribute_key TEXT, attribute_value TEXT)"
    )
    connection.executemany(
        "INSERT INTO student_attribute VALUES (?, 'home_state', ?)",
        [(f"s{i}", _home_state(i)) for i in range(200)],
    )
    connection.commit()
    connection.close()
    true_counts: dict[str, dict[str, int]] = {lens: {} for lens in ["all", *COHORTS]}
    for i in range(200):
        for lens in ("all", COHORTS[i % 3]):
            state = _home_state(i)
            true_counts[lens][state] = true_counts[lens].get(state, 0) + 1

    hidden = {}
    for lens in [*COHORTS, "all"]:
        rows = client.get(HOME_STATES, params={"cohort": lens}).json()["rows"]
        hidden[lens] = {row["state"] for row in rows if row["n"] is None}

    assert true_counts["all"]["NY"] == 31
    assert hidden == {
        "2021-22": {"NY", "IN"},
        "2022-23": {"NY", "IN"},
        "2023-24": {"NY", "IN"},
        "all": set(),
    }
    assert lone_lines(true_counts, hidden) == 0
    definition = client.get(HOME_STATES, params={"cohort": "all"}).json()["meta"]["definitions"]
    assert definition["Hidden"].endswith("or from the pooled cohorts minus the other years.")


@pytest.mark.usefixtures("published_model")
def test_kpis_follow_the_affinity_filter(client: TestClient, tmp_path: Path) -> None:
    """Students 0-49 play football: 40 of them are retained (0-39), so retention is 80%."""
    connection = sqlite3.connect(tmp_path / "model.db")
    connection.execute(
        "CREATE TABLE student_attribute (student_id TEXT, attribute_key TEXT, attribute_value TEXT)"
    )
    connection.executemany(
        "INSERT INTO student_attribute VALUES (?, 'affinity', ?)",
        [(f"s{i}", "Football" if i < 50 else "None") for i in range(200)],
    )
    connection.commit()
    connection.close()

    body = client.get(KPIS, params={"cohort": "all", "affinity": "football"}).json()

    retention = next(item for item in body["items"] if item["id"] == "retention")
    assert retention["detail"].startswith("40 of 50 students")
    assert "Affinity group: Football" in body["meta"]["filters"]


SUPPLEMENTAL = "/api/v1/sandbox/executive-view/supplemental"


@pytest.mark.usefixtures("model_db")
def test_supplemental_shows_each_file_as_uploaded_for_the_matching_students(
    client: TestClient, tmp_path: Path
) -> None:
    """A row per student with the file's columns in order, however few students a filter leaves."""
    connection = sqlite3.connect(tmp_path / "model.db")
    connection.execute(
        "CREATE TABLE student_attribute (attribute_id INTEGER, student_id TEXT, term_id INTEGER, "
        "attribute_key TEXT, attribute_value TEXT, source TEXT)"
    )
    empty = client.get(SUPPLEMENTAL, params={"cohort": "all"}).json()
    rows, attribute_id = [], 0
    for i in range(30):  # zip, then advisor; student 0 left advisor blank
        for key, value in (("home_zip", f"606{i:02d}"), ("advisor", "yes" if i % 2 else "no")):
            if not (i == 0 and key == "advisor"):
                attribute_id += 1
                rows.append(
                    (attribute_id, f"s{i}", None, key, value, "uploaded: a.csv, 2026-11-10")
                )
    rows.append((999, "s0", None, "affinity", "Band", "synthetic: affinity generator"))
    connection.executemany("INSERT INTO student_attribute VALUES (?, ?, ?, ?, ?, ?)", rows)
    connection.commit()
    connection.close()

    body = client.get(SUPPLEMENTAL, params={"cohort": "all"}).json()
    hispanic = client.get(SUPPLEMENTAL, params={"cohort": "all", "race": "hispanic"}).json()

    assert empty["files"] == []
    assert empty["meta"]["takeaway"].startswith("No supplemental data is loaded")
    [upload] = body["files"]
    assert (upload["file"], upload["uploaded_on"], upload["per_term"]) == (
        "a.csv",
        "2026-11-10",
        False,
    )
    assert upload["upload_id"] is None  # an older source, with no upload id in it
    assert upload["columns"] == ["home_zip", "advisor"]
    assert (upload["students"], upload["total_rows"]) == (30, 30)
    first = next(row for row in upload["rows"] if row["student_id"] == "s0")
    assert first["values"] == {"home_zip": "60600", "advisor": None}
    # 3 of the 30 are Hispanic (0, 10, 20): their rows show, even so few.
    [few] = hispanic["files"]
    assert few["students"] == 3
    assert sorted(row["student_id"] for row in few["rows"]) == ["s0", "s10", "s20"]


def test_a_built_in_sample_reads_as_its_file_name() -> None:
    """The data model's committed sample has its own source, with no upload date or id."""
    from app.sandbox.executive_view.supplemental import _parse_source

    built_in = "supplemental: all_students_extras.csv (built-in synthetic sample, seed 2026)"
    assert _parse_source(built_in) == ("all_students_extras.csv (built-in sample)", None, None)
    uploaded = "uploaded: aid.csv, 2026-11-10, 3f2a9c1b7d4e"
    assert _parse_source(uploaded) == ("aid.csv", "2026-11-10", "3f2a9c1b7d4e")


# The definitions behind the page's tooltips


@pytest.mark.usefixtures("published_model")
def test_every_tile_has_a_definition(client: TestClient) -> None:
    body = client.get(KPIS, params={"cohort": "2023-24"}).json()

    definitions = body["meta"]["definitions"]
    for kpi in body["items"]:
        assert kpi["label"] in definitions, f"{kpi['label']} has no definition to show"


def test_a_definition_is_short_enough_to_read_in_a_tooltip() -> None:
    from app.sandbox.executive_view.results import DEFINITION_LIMIT, measure_definitions

    for label, definition in measure_definitions().items():
        assert definition, f"{label} has no definition"
        assert len(definition) <= DEFINITION_LIMIT, f"{label} is {len(definition)} characters"


def test_a_definition_ends_on_a_whole_sentence() -> None:
    """Shortening keeps whole sentences, so a tooltip never trails off mid-clause."""
    from app.sandbox.executive_view.results import measure_definitions

    for label, definition in measure_definitions().items():
        assert definition.endswith("."), f"{label} ends mid-sentence: {definition[-40:]!r}"


def test_definitions_come_from_the_measures_own_notes() -> None:
    """Written once. The page, the published results and the chat all say the same thing."""
    from measures.calculations import retention

    from app.sandbox.executive_view.results import measure_definitions

    assert retention.NOTE.startswith(measure_definitions()["Retention"][:60])


@pytest.mark.usefixtures("published_model")
def test_the_gaps_card_explains_its_measures_and_keeps_its_own_notes(client: TestClient) -> None:
    body = client.get(GAPS, params={"cohort": "2023-24"}).json()

    definitions = body["meta"]["definitions"]
    assert "Retention" in definitions
    assert "Students behind" in definitions, "the card's own explanations must survive the merge"


EXPORT = "/api/v1/sandbox/executive-view/kpis/students.csv"


@pytest.mark.usefixtures("model_db")
def test_export_lists_each_student_with_the_tiles_answers(client: TestClient) -> None:
    """Planted: 120 of 200 retained, 20 persisted, half through each gateway, 50 graduated."""
    import csv
    import io

    response = client.get(EXPORT, params={"cohort": "all"})
    one = client.get(EXPORT, params={"cohort": "all", "measure": "retention", "race": "hispanic"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "executive_view_students_all_all_measures.csv" in response.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 200
    measures = [column for column in rows[0] if column not in ("Student_GUID", "Cohort")]
    yes = {column: sum(row[column] == "Yes" for row in rows) for column in measures}
    assert yes == {
        "Retention": 120,
        "Persistence_Elsewhere": 20,
        "Gateway_Math": 100,
        "Gateway_English": 100,
        "Graduation": 50,
    }
    # One measure, one filter: only that column, for the 21 Hispanic students, 12 retained.
    hispanic = list(csv.DictReader(io.StringIO(one.text)))
    assert list(hispanic[0]) == ["Student_GUID", "Cohort", "Retention"]
    assert (len(hispanic), sum(row["Retention"] == "Yes" for row in hispanic)) == (21, 12)


# Reading the published results


def _hand_written(hispanic_hidden: bool) -> list[tuple]:
    """Pool rows unlike the planted model's: everyone is 50 of 100, Hispanic 10 of 20 or hidden."""
    rows = []
    for measure in KPI_MEASURES:
        rows.append(row("all", "all", 0.5, 100, measure=measure, cohort=POOL))
        if hispanic_hidden:
            rows.append(row("race", "Hispanic", None, None, measure=measure, cohort=POOL))
        else:
            rows.append(row("race", "Hispanic", 0.5, 20, measure=measure, cohort=POOL))
        rows.append(row("race", "White", 0.5, 80, measure=measure, cohort=POOL))
    return rows


@pytest.mark.usefixtures("model_db")
def test_unfiltered_tiles_are_the_published_rows(client: TestClient, publish_results) -> None:
    """The four measures come from the published file, not the model; graduation stays live."""
    publish_results(EXEC_MANIFEST, _hand_written(hispanic_hidden=False))

    body = client.get(KPIS, params={"cohort": "all"}).json()

    values = {item["id"]: item["value"] for item in body["items"]}
    assert values == {
        "retention": 50.0,
        "persistence": 50.0,
        "gateway_math": 50.0,
        "gateway_english": 50.0,
        "graduation": 25.0,
    }
    assert body["items"][0]["detail"].startswith("50 of 100 students")
    assert [(spec["measure"], spec["cohort"], spec["where"]) for spec in body["meta"]["specs"]] == [
        (measure, POOL, {}) for measure in KPI_MEASURES
    ]


@pytest.mark.usefixtures("model_db")
def test_a_filter_on_a_published_group_reads_its_row_hidden_or_not(
    client: TestClient, publish_results
) -> None:
    """Hispanic is hidden in the published file, so its tiles are hidden here too.

    Counted live, the 21 Hispanic students would show. Graduation isn't published, so it stays.
    """
    publish_results(EXEC_MANIFEST, _hand_written(hispanic_hidden=True))

    body = client.get(KPIS, params={"cohort": "all", "race": "hispanic"}).json()

    assert [item["id"] for item in body["items"]] == ["graduation"]
    assert [spec["where"] for spec in body["meta"]["specs"]] == [{"race": "Hispanic"}] * 4


@pytest.mark.usefixtures("model_db")
@pytest.mark.parametrize("hispanic_hidden", [True, False])
def test_a_live_tile_is_hidden_when_one_filter_broader_is_hidden(
    client: TestClient, publish_results, hispanic_hidden: bool
) -> None:
    """First generation isn't published, so Hispanic and not reported is counted live.

    Dropping first generation leaves Hispanic. When the published file hides it, live tiles for its
    parts could add back up to it, so they're hidden. Everyone is not reported: live, 12 of 21.
    """
    publish_results(EXEC_MANIFEST, _hand_written(hispanic_hidden))
    params = {"cohort": "all", "race": "hispanic", "first_gen": "not_reported"}

    body = client.get(KPIS, params=params).json()

    assert body["meta"]["specs"] == []
    if hispanic_hidden:
        assert [item["id"] for item in body["items"]] == ["graduation"]
    else:
        retention = next(item for item in body["items"] if item["id"] == "retention")
        assert retention["detail"].startswith("12 of 21 students")


def _add_affinity(model: Path, value: str) -> None:
    """Give every planted student the same synthetic affinity group."""
    connection = sqlite3.connect(model)
    connection.execute(
        "CREATE TABLE student_attribute (student_id TEXT, attribute_key TEXT, attribute_value TEXT)"
    )
    connection.executemany(
        "INSERT INTO student_attribute VALUES (?, 'affinity', ?)",
        [(f"s{i}", value) for i in range(200)],
    )
    connection.commit()
    connection.close()


@pytest.mark.usefixtures("model_db")
@pytest.mark.parametrize("hispanic_hidden", [True, False])
def test_a_live_tile_is_hidden_when_any_broader_published_group_is_hidden(
    client: TestClient, tmp_path: Path, publish_results, hispanic_hidden: bool
) -> None:
    """Three filters, only race published: Hispanic is two filters broader than the tile.

    Dropping one filter leaves race with first generation or affinity, neither published, so only
    checking every smaller set of the filters finds the hidden Hispanic group. The fixture's
    manifest publishes no affinity, so affinity is counted live here.
    """
    _add_affinity(tmp_path / "model.db", "None")
    publish_results(EXEC_MANIFEST, _hand_written(hispanic_hidden))
    params = {
        "cohort": "all",
        "race": "hispanic",
        "first_gen": "not_reported",
        "affinity": "none",
    }

    body = client.get(KPIS, params=params).json()

    assert body["meta"]["specs"] == []
    if hispanic_hidden:
        assert [item["id"] for item in body["items"]] == ["graduation"]
    else:
        retention = next(item for item in body["items"] if item["id"] == "retention")
        assert retention["detail"].startswith("12 of 21 students")


def _two_single_cohorts(female_hidden_before: bool) -> list[tuple]:
    """Everyone and female rows for 2022-23 and 2023-24; female is hidden in 2022-23 if asked."""
    rows = []
    for measure in KPI_MEASURES:
        rows.append(row("all", "all", 0.5, 100, measure=measure, cohort=POOL))
        for year in ("2022-23", "2023-24"):
            hidden = female_hidden_before and year == "2022-23"
            rows.append(row("all", "all", 0.5, 100, measure=measure, cohort=year))
            rate, n = (None, None) if hidden else (0.5, 100)
            rows.append(row("gender", "F", rate, n, measure=measure, cohort=year))
    return rows


@pytest.mark.usefixtures("model_db")
@pytest.mark.parametrize("female_hidden_before", [True, False])
def test_a_live_tile_has_no_arrow_when_its_tile_the_year_before_is_hidden(
    client: TestClient,
    publish_results,
    monkeypatch: pytest.MonkeyPatch,
    female_hidden_before: bool,
) -> None:
    """Female and not reported is live. Its arrow compares with 2022-23's tile for the same
    filters, which the page hides when the published female group is hidden that year.

    Filters on 2023-24 show published groups only. The rule is the same on 2024-25 against
    2023-24, which the planted model has no students in, so live counting is let through here.
    """
    monkeypatch.setattr(cohorts, "withholds_live_filters", lambda lens: False)
    publish_results(EXEC_MANIFEST, _two_single_cohorts(female_hidden_before))
    params = {"cohort": "2023-24", "gender": "female", "first_gen": "not_reported"}

    body = client.get(KPIS, params=params).json()

    retention = next(item for item in body["items"] if item["id"] == "retention")
    assert retention["value"] == 60.6  # every planted student is female and not reported
    if female_hidden_before:
        assert retention["trend"] is None
    else:
        assert retention["trend"]["label"] == "+1.5% vs 2022-23"


@pytest.mark.usefixtures("model_db")
def test_a_pooled_bar_counts_a_hidden_or_missing_year_as_zero(
    client: TestClient, publish_results
) -> None:
    """Hispanic is behind in the pool. 2021-22 has 5 behind, 2022-23 hides Hispanic, and
    2023-24 has no Hispanic row at all (as the deploy's copy can leave one out)."""
    rows = [row("all", "all", 0.5, 100, measure=m, cohort=POOL) for m in KPI_MEASURES]
    rows.append(row("race", "Hispanic", 0.4, 30, measure="retention", cohort=POOL))
    for year in COHORTS:
        rows.append(row("all", "all", 0.5, 100, measure="retention", cohort=year))
    rows.append(row("race", "Hispanic", 0.4, 10, measure="retention", cohort="2021-22"))
    rows.append(row("race", "Hispanic", None, None, measure="retention", cohort="2022-23"))
    rows.append(row("race", "White", 0.5, 90, measure="retention", cohort="2023-24"))
    gaps = [
        gap("race", "Hispanic", -12.0, -4.0, measure="retention", cohort=POOL),
        gap("race", "Hispanic", -50.0, -5.0, measure="retention", cohort="2021-22"),
        gap(
            "race",
            "Hispanic",
            None,
            None,
            measure="retention",
            cohort="2022-23",
            status="suppressed",
        ),
    ]
    publish_results(EXEC_MANIFEST, rows, gaps)

    body = client.get(GAPS, params={"cohort": "all"}).json()

    [hispanic] = body["rows"]
    assert hispanic["group"] == "Hispanic"
    assert hispanic["by_cohort"] == [
        {"cohort": "2021-22", "students_behind": 5},
        {"cohort": "2022-23", "students_behind": 0},
        {"cohort": "2023-24", "students_behind": 0},
    ]


@pytest.mark.usefixtures("published_model")
def test_a_filter_that_is_not_published_is_counted_live(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every planted student's first generation is not reported, so the numbers match everyone's.

    Live counting is let through on 2023-24, as on 2024-25, so the arrows can be compared too.
    """
    monkeypatch.setattr(cohorts, "withholds_live_filters", lambda lens: False)
    shared = client.get(KPIS, params={"cohort": "2023-24"}).json()
    live = client.get(KPIS, params={"cohort": "2023-24", "first_gen": "not_reported"}).json()

    def numbers(items: list[dict]) -> list[tuple]:
        return [(item["id"], item["value"], item["detail"], item["trend"]) for item in items]

    assert numbers(live["items"]) == numbers(shared["items"])
    assert live["meta"]["specs"] == []
    assert len(shared["meta"]["specs"]) == 4


@pytest.mark.usefixtures("published_model")
def test_a_single_cohort_hides_what_its_published_row_hides(client: TestClient) -> None:
    """2023-24 has 7 Hispanic students, so the published row and the tile are both hidden."""
    body = client.get(KPIS, params={"cohort": "2023-24", "race": "hispanic"}).json()

    assert [item["id"] for item in body["items"]] == []
    assert body["meta"]["specs"][0]["cohort"] == "2023-24"


WITHHELD = "Single pooled years: filters show published groups only"


@pytest.mark.usefixtures("published_model")
@pytest.mark.parametrize("active", [{"goal": "associate"}, {"first_gen": "not_reported"}])
def test_a_single_pooled_year_counts_no_filter_live(
    client: TestClient, active: dict[str, str]
) -> None:
    """Beside the pool, a live 2023-24 tile could be worked out from the pool minus the other years.

    Goal and first generation aren't published groups, so nothing shows, graduation included. The
    planted model has no goal column: withholding is decided before any count is asked for. With
    no tiles there are no arrows, so the arrow chips are left off too.
    """
    body = client.get(KPIS, params={"cohort": "2023-24", **active}).json()

    assert body["items"] == []
    assert body["meta"]["specs"] == []
    assert WITHHELD in body["meta"]["filters"]
    assert not any(chip.startswith("Arrows:") for chip in body["meta"]["filters"])


@pytest.mark.usefixtures("published_model")
def test_a_single_pooled_year_shows_a_published_group_without_graduation(
    client: TestClient,
) -> None:
    """Every planted student is female, so the published female row is everyone's, shown."""
    body = client.get(KPIS, params={"cohort": "2023-24", "gender": "female"}).json()

    assert "Arrows: relative change vs 2022-23" in body["meta"]["filters"]

    assert [item["id"] for item in body["items"]] == KPI_MEASURES
    assert body["items"][0]["value"] == 60.6
    assert [spec["where"] for spec in body["meta"]["specs"]] == [{"gender": "F"}] * 4
    assert WITHHELD in body["meta"]["filters"]


@pytest.mark.usefixtures("published_model")
def test_the_pooled_lens_still_counts_filters_live(client: TestClient) -> None:
    """The pool and 2024-25 aren't withheld: first generation is counted live, graduation too."""
    body = client.get(KPIS, params={"cohort": "all", "first_gen": "not_reported"}).json()

    assert [item["id"] for item in body["items"]] == [*KPI_MEASURES, "graduation"]
    assert body["meta"]["specs"] == []
    assert WITHHELD not in body["meta"]["filters"]


def _move_a_cohort_to_2024_25(model: Path) -> None:
    """Relabel the planted 2021-22 cohort and its first fall as 2024-25, the year after 2023-24."""
    connection = sqlite3.connect(model)
    connection.execute("UPDATE cohort_membership SET cohort = '2024-25' WHERE cohort = '2021-22'")
    connection.execute("UPDATE term SET academic_year = '2024-25' WHERE term_id = 1")
    connection.commit()
    connection.close()


@pytest.mark.usefixtures("model_db")
def test_a_2024_25_tile_has_no_arrow_against_a_withheld_2023_24_tile(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2023-24 withholds first generation's live tiles and graduation, so an arrow on 2024-25
    would give their rates back: the arrow's change and 2024-25's rate make 2023-24's.

    Retention and persistence have no arrow on 2024-25 anyway (year 2). Without the withholding,
    gateway and graduation would have theirs.
    """
    _move_a_cohort_to_2024_25(tmp_path / "model.db")
    params = {"cohort": "2024-25", "first_gen": "not_reported"}

    body = client.get(KPIS, params=params).json()
    monkeypatch.setattr(cohorts, "withholds_live_filters", lambda lens: False)
    unwithheld = client.get(KPIS, params=params).json()

    assert [item["id"] for item in body["items"]] == [*KPI_MEASURES, "graduation"]
    assert [item["trend"] for item in body["items"]] == [None] * 5
    trends = {item["id"]: item["trend"] for item in unwithheld["items"]}
    assert all(trends[name] is not None for name in ("gateway_math", "graduation"))


@pytest.mark.usefixtures("published_model")
@pytest.mark.parametrize("params", [{}, {"gender": "female"}])
def test_a_cohort_short_of_year_2_shows_retention_so_far_without_an_arrow(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, str]
) -> None:
    """Retention and persistence need year 2: against a finished cohort, the share so far
    would read as a drop. The planted model's newest cohort is 2023-24, so it stands in for
    2024-25. Gateway is a year-1 measure and keeps its arrow; graduation keeps its own rule."""
    monkeypatch.setattr(cohorts, "PARTLY_OBSERVED", "2023-24")
    body = client.get(KPIS, params={"cohort": "2023-24", **params}).json()
    items = {item["id"]: item for item in body["items"]}

    for name in ("retention", "persistence"):
        assert items[name]["trend"] is None
        assert items[name]["detail"].endswith(
            "; year 2 isn't fully observed yet, so this will likely rise"
        )
    assert items["retention"]["value"] == 60.6
    for name in ("gateway_math", "gateway_english"):
        assert items[name]["trend"] is not None
        assert "year 2 isn't fully observed" not in items[name]["detail"]


def test_only_year_2_measures_on_the_partly_observed_cohort_are_short_of_it() -> None:
    assert cohorts.short_of_year_2("retention", "2024-25")
    assert cohorts.short_of_year_2("persistence", "2024-25")
    assert not cohorts.short_of_year_2("gateway_math", "2024-25")
    assert not cohorts.short_of_year_2("graduation", "2024-25")
    assert not cohorts.short_of_year_2("retention", "2023-24")
    assert not cohorts.short_of_year_2("retention", "all")


@pytest.mark.usefixtures("published_model")
def test_the_gaps_card_lists_its_specs(client: TestClient) -> None:
    """Three measures by five one-way breakdowns, with gaps, for the lens's own cohort."""
    specs = client.get(GAPS, params={"cohort": "all"}).json()["meta"]["specs"]

    assert len(specs) == 15
    assert {spec["cohort"] for spec in specs} == {POOL}
    assert {spec["measure"] for spec in specs} == {"retention", "gateway_math", "gateway_english"}
    assert {tuple(spec["group_by"]) for spec in specs} == {
        ("race",),
        ("gender",),
        ("pell",),
        ("age_band",),
        ("enrollment_intensity",),
    }
    assert all(spec["include"] == ["rates", "gaps"] for spec in specs)


@pytest.mark.usefixtures("model_db")
@pytest.mark.parametrize("path", [KPIS, GAPS])
def test_unpublished_results_are_a_503(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    manifest = tmp_path / "exec_manifest.yaml"
    manifest.write_text(EXEC_MANIFEST, encoding="utf-8")
    missing = builder.ResultsReader(manifest, tmp_path / "missing.sqlite")
    monkeypatch.setattr(published, "reader", lambda: missing)

    response = client.get(path, params={"cohort": "all"})

    assert response.status_code == 503
    assert "missing.sqlite not found" in response.text


@pytest.mark.usefixtures("model_db")
@pytest.mark.parametrize("params", [{}, {"race": "hispanic"}, {"race": "hispanic", "pell": "no"}])
def test_a_manifest_that_cant_be_parsed_is_a_503(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, params: dict
) -> None:
    """Unfiltered, a published group, and live with the subset rule all read the manifest."""
    manifest = tmp_path / "broken.yaml"
    manifest.write_text("version: [5\ncohorts: {", encoding="utf-8")
    broken = builder.ResultsReader(manifest, tmp_path / "missing.sqlite")
    monkeypatch.setattr(published, "reader", lambda: broken)

    response = client.get(KPIS, params={"cohort": "all", **params})

    assert response.status_code == 503


@pytest.fixture
def real_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> builder.ResultsReader:
    """The builder over the repo's own manifest. Approvals need no results file."""
    reader = builder.ResultsReader(REPO / "measures" / "manifest.yaml", tmp_path / "none.sqlite")
    monkeypatch.setattr(published, "reader", lambda: reader)
    return reader


def test_the_manifest_publishes_every_lens_the_page_reads(real_manifest) -> None:
    """Each headline measure has the pool and each single year, by the gaps card's breakdowns."""
    from app.sandbox.executive_view import published as executive

    approved = real_manifest.approved()
    singles = real_manifest._manifest()["single_measures"]
    for measure in KPI_MEASURES:
        assert cohorts.POOL in approved[measure]["cohorts"]
        assert set(cohorts.SINGLE_YEARS) <= set(approved[measure]["cohorts"])
        for dimension in executive.GAP_DIMENSIONS:
            assert frozenset([dimension]) in singles[measure]
    assert list(results._GAP_MEASURES) == ["retention", "gateway_math", "gateway_english"]


@pytest.mark.usefixtures("real_manifest")
@pytest.mark.parametrize(
    ("lens", "active", "group"),
    [
        ("all", {"age": "over_20_to_24"}, {"age_band": "> 20-24"}),
        ("2023-24", {"pell": "yes"}, {"pell": "Y"}),
        ("2023-24", {"race": "unknown"}, {"race": "UNKNOWN"}),
        ("2024-25", {"gender": "x"}, {"gender": "X"}),
        ("all", {"affinity": "band"}, {"affinity": "Band"}),
        # Affinity and race x gender are published for the pool only.
        ("2023-24", {"affinity": "band"}, None),
        ("all", {"race": "hispanic", "gender": "female"}, {"race": "Hispanic", "gender": "F"}),
        ("2023-24", {"race": "hispanic", "gender": "female"}, None),
        # Goal, program and first generation aren't published dimensions.
        ("all", {"goal": "associate"}, None),
        ("all", {"program": "240101"}, None),
        ("all", {"race": "hispanic", "first_gen": "yes"}, None),
        ("all", {}, None),
    ],
)
def test_filters_map_to_a_published_group_only_when_it_is_approved(
    lens: str, active: dict[str, str], group: dict[str, str] | None
) -> None:
    from app.sandbox.executive_view import published as executive

    assert executive.filter_group(lens, active) == group
