"""The equity card and action board hide their groups across the pool and its years.

Every count is planted per lens, so each line can be checked by hand. The data is synthetic.
"""

import pytest
from fastapi.testclient import TestClient

from app.sandbox.executive_view import cohorts
from app.sandbox.student_success import actions, equity
from tests.test_sandbox_executive_view_small_counts import lone_lines

EQUITY = "/api/v1/sandbox/student-success/equity"
ACTIONS = "/api/v1/sandbox/student-success/actions"
POOL_LENSES = [*cohorts.POOL_YEARS, "all"]

# Students by gender in each lens. Gender X is 7 in 2022-23, hidden; the pooled 30 minus 12 and
# 11 would give it back, so a year's X is hidden too. 2024-25 is outside the pool, on its own.
GENDER = {
    "2021-22": {"F": 100, "M": 90, "X": 12},
    "2022-23": {"F": 110, "M": 95, "X": 7},
    "2023-24": {"F": 105, "M": 98, "X": 11},
    "all": {"F": 315, "M": 283, "X": 30},
    "2024-25": {"F": 120, "M": 100, "X": 4},
}
LABELS = {"F": "Female", "M": "Male", "X": "Gender X"}
# One program's students by gender: Gender X's 4 in 2022-23 is the pool's only X.
PROGRAM = {
    "2021-22": {"F": 30, "M": 25},
    "2022-23": {"F": 28, "M": 20, "X": 4},
    "2023-24": {"F": 26, "M": 22},
    "all": {"F": 84, "M": 67, "X": 4},
    "2024-25": {"F": 31, "M": 27, "X": 3},
}


def _lens(years: list[str]) -> str:
    """The lens a query's cohort years belong to."""
    return "all" if years == cohorts.POOL_YEARS else years[0]


def _board_row(code: str, n: int) -> list:
    """A board row: students, stopped out, near 15, near 6, gateway, priority, MVSU priority."""
    return [code, n, n // 2, n // 3, n // 4, n // 5, n // 6, n // 7]


@pytest.fixture
def planted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer each card's queries from the planted counts for the lens the query asks about."""

    def fake_fetch(sql: str, params: list[str] | None = None) -> list[list]:
        """The planted rows for one query, by what it selects and which cohorts it counts."""
        if "LIMIT 1" in sql:
            return [["2025-26"]]
        if "math_or_english_gateway" in sql:
            return []
        if "SUM(stopped_out)" in sql:
            # The board's query takes the latest year first, then the cohorts.
            counts = GENDER[_lens(list(params or [])[1:])]
            return [_board_row(code, n) for code, n in counts.items()]
        if "program_of_study" in sql:
            counts = PROGRAM[_lens(list(params or []))]
            return [["240101", code, n] for code, n in counts.items()]
        counts = GENDER[_lens(list(params or []))]
        return [[code, n, n // 2, n // 3, n // 4] for code, n in counts.items()]

    monkeypatch.setattr(equity.credentials, "_fetch", fake_fetch)
    monkeypatch.setattr(equity, "_retention_gaps", lambda dimension, years: {})
    monkeypatch.setattr(equity.results, "_measure_counts", lambda name, years: None)
    monkeypatch.setattr(actions, "_dfw_outcomes", lambda: {})


def _labelled(counts: dict[str, int]) -> dict[str, int]:
    """Planted counts by the cards' group labels."""
    return {LABELS[code]: n for code, n in counts.items()}


def _hidden_groups(client: TestClient, lens: str) -> dict[str, set[str]]:
    """The groups each card hides in a lens: the equity card's sizes and segments, the board's n."""
    body = client.get(EQUITY, params={"cohort": lens, "dimension": "gender"}).json()
    board = client.get(ACTIONS, params={"cohort": lens, "dimension": "gender"}).json()
    [program] = body["programs"]
    return {
        "equity": {group["group"] for group in body["groups"] if group["n"] is None},
        "segments": {cell["group"] for cell in program["segments"] if cell["n"] is None},
        "board": {row["group"] for row in board["groups"] if row["n"] is None},
    }


@pytest.mark.usefixtures("planted")
def test_equity_groups_leave_no_lone_hidden_group_across_the_pool(client: TestClient) -> None:
    """Hidden in 2022-23 alone, Gender X would be the pool's 30 minus 12 and 11."""
    hidden = {lens: _hidden_groups(client, lens)["equity"] for lens in POOL_LENSES}

    assert hidden == {
        "2021-22": {"Gender X", "Male"},
        "2022-23": {"Gender X", "Male"},
        "2023-24": {"Gender X", "Male"},
        "all": set(),
    }
    sizes = {lens: _labelled(GENDER[lens]) for lens in POOL_LENSES}
    assert lone_lines(sizes, hidden) == 0


@pytest.mark.usefixtures("planted")
def test_equity_and_board_hide_the_same_groups(client: TestClient) -> None:
    """Both count every student in the cohort by group, so a size one shows the other must too."""
    for lens in [*POOL_LENSES, "2024-25"]:
        hidden = _hidden_groups(client, lens)
        assert hidden["equity"] == hidden["board"], lens


@pytest.mark.usefixtures("planted")
def test_every_board_column_leaves_no_lone_hidden_group(client: TestClient) -> None:
    """Each column adds up to its tile, and its pooled count is the sum of its years'."""
    columns = {"n": 1, "stopped_out": 2, "near_15": 3, "gateway": 5, "priority": 6}
    rows = {
        lens: client.get(ACTIONS, params={"cohort": lens, "dimension": "gender"}).json()["groups"]
        for lens in POOL_LENSES
    }
    for column, index in columns.items():
        counts = {
            lens: {LABELS[code]: _board_row(code, n)[index] for code, n in GENDER[lens].items()}
            for lens in POOL_LENSES
        }
        hidden = {
            lens: {row["group"] for row in rows[lens] if row[column] is None} for lens in rows
        }
        assert lone_lines(counts, hidden) == 0, column


@pytest.mark.usefixtures("planted")
def test_program_segments_leave_no_lone_hidden_group(client: TestClient) -> None:
    """The program's 4 Gender X students in 2022-23 are hidden, with a cover in that year and the
    pool, so neither the program's total nor the pool gives them back."""
    hidden = {lens: _hidden_groups(client, lens)["segments"] for lens in POOL_LENSES}

    assert "Gender X" in hidden["2022-23"] and "Gender X" in hidden["all"]
    segments = {lens: _labelled(PROGRAM[lens]) for lens in POOL_LENSES}
    assert lone_lines(segments, hidden) == 0


@pytest.mark.usefixtures("planted")
def test_a_cohort_outside_the_pool_gets_a_cover_too(client: TestClient) -> None:
    """2024-25's 4 Gender X students are the only small group: Male, the smaller shown, covers."""
    hidden = _hidden_groups(client, "2024-25")
    body = client.get(EQUITY, params={"cohort": "2024-25", "dimension": "gender"}).json()

    assert hidden == {
        "equity": {"Gender X", "Male"},
        "segments": {"Gender X", "Male"},
        "board": {"Gender X", "Male"},
    }
    female = next(group for group in body["groups"] if group["group"] == "Female")
    assert female["n"] == 120
    male = next(group for group in body["groups"] if group["group"] == "Male")
    assert male["share"] is None and male["milestones"] == [None, None, None]
    assert body["meta"]["definitions"]["Hidden"].endswith(
        "or from the pooled cohorts minus the other years."
    )
