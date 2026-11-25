"""The executive view's rule for hiding counts that a small group could be worked out from."""

import pytest

from app.sandbox.executive_view.small_counts import hide_across_lenses, hide_with_cover, is_small

POOL_LENSES = ["2021-22", "2022-23", "2023-24", "all"]


def lone_lines(by_lens: dict[str, dict[str, int]], hidden: dict[str, set[str]]) -> int:
    """How many lines have exactly one hidden count that the rest of the line gives back.

    The lines are each lens's counts (they add up to its total) and, across the pool's lenses,
    each key (the pooled count is the sum of its years'). The hidden count comes back from the
    counts shown beside it or, when it is the line's only count, from the line's total, which is
    shown at 10 or more. A count of 0 is neither shown nor hidden.
    """
    lines = [[(lens, key) for key in counts] for lens, counts in by_lens.items()]
    if len(by_lens) > 1:
        keys = {key for counts in by_lens.values() for key in counts}
        lines += [[(lens, key) for lens in by_lens] for key in keys]
    found = 0
    for line in lines:
        counted = [(lens, key) for lens, key in line if by_lens[lens].get(key, 0) > 0]
        hidden_cells = [(lens, key) for lens, key in counted if key in hidden[lens]]
        if len(hidden_cells) != 1:
            continue
        [(lens, key)] = hidden_cells
        if len(counted) > 1 or not is_small(by_lens[lens][key]):
            found += 1
    return found


def test_one_to_nine_is_small_and_zero_is_not() -> None:
    assert [is_small(n) for n in (0, 1, 9, 10)] == [False, True, True, False]


def test_a_lone_hidden_group_gets_the_smallest_shown_group_as_cover() -> None:
    """Pell unknown is 5, so Pell yes (60), the smaller shown value, is hidden too."""
    assert hide_with_cover({"yes": 60, "no": 74, "unknown": 5}) == {"unknown", "yes"}


def test_two_hidden_groups_need_no_cover() -> None:
    assert hide_with_cover({"a": 100, "b": 4, "c": 3}) == {"b", "c"}


def test_a_group_of_zero_needs_no_cover() -> None:
    assert hide_with_cover({"a": 100, "b": 40, "c": 0}) == set()


def test_ties_pick_the_same_cover_every_time() -> None:
    assert hide_with_cover({"b": 14, "a": 14, "c": 2}) == {"a", "c"}


@pytest.mark.parametrize(
    "counts",
    [
        {"yes": 60, "no": 74, "unknown": 5},
        {"a": 100, "b": 4, "c": 3},
        {"a": 100, "b": 40, "c": 0},
        {"b": 14, "a": 14, "c": 2},
        {"IL": 150, "IN": 45, "WI": 5, "OH": 0, "MI": 12},
    ],
)
def test_one_lens_hides_as_one_line_does(counts: dict[str, int]) -> None:
    """2024-25 is outside the pool, so it is checked alone, by the one-line rule."""
    assert hide_across_lenses({"2024-25": counts}) == {"2024-25": hide_with_cover(counts)}


def test_a_year_given_back_by_the_pool_is_covered_by_another_year() -> None:
    """NY is 13, 8 and 10 in the pool's years, 31 pooled: 31 - 13 - 10 gives back the 8.

    Within 2022-23 the 8 already has IN as its cover. Across the lenses, 2023-24's NY (10), the
    smallest shown year, is hidden too. That leaves NY alone hidden in 2023-24, so its IN is, and
    so on until no line has one hidden count. The pool keeps every count.
    """
    by_lens = {
        "2021-22": {"IL": 300, "NY": 13, "IN": 50},
        "2022-23": {"IL": 310, "NY": 8, "IN": 60},
        "2023-24": {"IL": 320, "NY": 10, "IN": 55},
        "all": {"IL": 930, "NY": 31, "IN": 165},
    }

    hidden = hide_across_lenses(by_lens)

    assert hidden == {
        "2021-22": {"NY", "IN"},
        "2022-23": {"NY", "IN"},
        "2023-24": {"NY", "IN"},
        "all": set(),
    }
    # Each lens on its own, as before, hides NY and IN in 2022-23 only: the pool gives both back.
    one_at_a_time = {lens: hide_with_cover(counts) for lens, counts in by_lens.items()}
    assert lone_lines(by_lens, one_at_a_time) == 2
    assert lone_lines(by_lens, hidden) == 0


def test_a_year_covers_before_the_pool_on_a_tie() -> None:
    """The pool counts a student in two of its years once (home states), so it can tie a year."""
    by_lens = {
        "2021-22": {"IL": 100, "NY": 5},
        "2022-23": {"IL": 100, "NY": 20},
        "2023-24": {"IL": 100},
        "all": {"IL": 300, "NY": 20},
    }

    hidden = hide_across_lenses(by_lens)

    assert "NY" in hidden["2022-23"] and "NY" not in hidden["all"]
    assert lone_lines(by_lens, hidden) == 0


def test_the_pool_covers_only_when_no_year_can() -> None:
    """NY is hidden in 2021-22 as WI's cover, and no other year has NY: the pool's NY equals it."""
    by_lens = {
        "2021-22": {"IL": 100, "NY": 12, "WI": 4},
        "2022-23": {"IL": 100},
        "2023-24": {"IL": 100},
        "all": {"IL": 300, "NY": 12, "WI": 4},
    }

    hidden = hide_across_lenses(by_lens)

    assert hidden == {
        "2021-22": {"NY", "WI"},
        "2022-23": set(),
        "2023-24": set(),
        "all": {"NY", "WI"},
    }
    assert lone_lines(by_lens, hidden) == 0


def test_a_cover_is_never_the_only_count_in_another_line() -> None:
    """2022-23 has only g and 2023-24 only h, so hiding either covers nothing: each equals its
    year's total. The pool's g and h cover instead, so 2021-22's g isn't 20 - 15."""
    by_lens = {
        "2021-22": {"g": 5, "h": 50},
        "2022-23": {"g": 15},
        "2023-24": {"h": 40},
        "all": {"g": 20, "h": 90},
    }

    hidden = hide_across_lenses(by_lens)

    assert hidden == {"2021-22": {"g", "h"}, "2022-23": set(), "2023-24": set(), "all": {"g", "h"}}
    assert lone_lines(by_lens, hidden) == 0
    # Covers that are a whole year each leave both of those lines giving them back.
    whole_years = {"2021-22": {"g", "h"}, "2022-23": {"g"}, "2023-24": {"h"}, "all": set()}
    assert lone_lines(by_lens, whole_years) == 2


def test_lines_are_checked_in_the_order_found() -> None:
    """Gender X (1 student) in 2022-23 and the pool: the pool's Unknown and 2022-23's cover it.

    Checking each cover's lines after the lines already waiting keeps the covers near the lone
    count, rather than spreading them along the latest cover's lines first.
    """
    by_lens = {
        "2021-22": {"F": 1336, "M": 1078, "U": 90},
        "2022-23": {"F": 1410, "X": 1, "M": 1103, "U": 103},
        "2023-24": {"F": 1397, "M": 1051, "U": 132},
        "all": {"F": 4143, "X": 1, "M": 3232, "U": 325},
    }

    hidden = hide_across_lenses(by_lens)

    assert hidden == {"2021-22": set(), "2022-23": {"U", "X"}, "2023-24": set(), "all": {"U", "X"}}
    assert lone_lines(by_lens, hidden) == 0


def test_a_year_with_none_of_a_key_needs_no_cover() -> None:
    """NY is 0 in 2022-23, which is nobody to protect, so nothing is hidden."""
    by_lens = {
        "2021-22": {"IL": 100, "NY": 20},
        "2022-23": {"IL": 100},
        "2023-24": {"IL": 100, "NY": 15},
        "all": {"IL": 300, "NY": 35},
    }

    assert hide_across_lenses(by_lens) == {lens: set() for lens in POOL_LENSES}
