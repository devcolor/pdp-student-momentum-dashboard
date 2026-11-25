"""Which counts the executive view hides so a small group can't be worked out by subtraction.

The rule matches the shared measures' (measures/run_measures.py, hide_complements): a group of
1 to 9 students is hidden, and when a line that adds up to a shown total has exactly one hidden
group, its smallest shown group is hidden too. A group of 0 needs no cover. Hiding is display
protection, not a guarantee (measures/README.md, Rules).
"""

from collections import defaultdict, deque

MIN_GROUP_SIZE = 10
# The pooled lens: each of its counts is the sum of its years'.
_POOLED = "all"


def is_small(count: int) -> bool:
    """True for 1 to 9 students: too few to show. Zero is not small; there's nobody to protect."""
    return 0 < count < MIN_GROUP_SIZE


def hide_with_cover(counts: dict[str, int]) -> set[str]:
    """The keys to hide in one line: every small group, plus a cover when exactly one is small."""
    hidden = {key for key, count in counts.items() if is_small(count)}
    if len(hidden) == 1:
        shown = [key for key, count in counts.items() if count >= MIN_GROUP_SIZE]
        if shown:
            hidden.add(min(shown, key=lambda key: (counts[key], key)))
    return hidden


def hide_across_lenses(by_lens: dict[str, dict[str, int]]) -> dict[str, set[str]]:
    """The keys to hide in each lens, until no line has exactly one hidden count beside a total.

    by_lens holds one lens's counts, or the pool's years and the pool (cohorts.lenses_with). The
    lines are each lens's counts, which add up to its total, and each key across the lenses, whose
    pooled count is the sum of its years'. A line with exactly one hidden count hides its smallest
    shown count too, a year's before the pool's, and that cover's own lines are checked again, in
    the order they were found. With one lens it is hide_with_cover. Lines are checked one at a
    time, not solved together, as in the shared measures (measures/README.md, Rules).
    """
    hidden = {
        lens: {key for key, count in counts.items() if is_small(count)}
        for lens, counts in by_lens.items()
    }
    lines = [[(lens, key) for key in sorted(counts)] for lens, counts in by_lens.items()]
    if len(by_lens) > 1:
        keys = sorted({key for counts in by_lens.values() for key in counts})
        lines += [[(lens, key) for lens in by_lens] for key in keys]
    lines_with: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, line in enumerate(lines):
        for cell in line:
            lines_with[cell].append(index)

    def count(cell: tuple[str, str]) -> int:
        """One cell's count; a key a lens doesn't have counts 0."""
        lens, key = cell
        return by_lens[lens].get(key, 0)

    def cover_order(cell: tuple[str, str]) -> tuple[bool, int, str, str]:
        """Smallest first, a year's before the pool's, then by name so ties always pick the same."""
        lens, key = cell
        return (lens == _POOLED, count(cell), lens, key)

    def is_whole_line(cell: tuple[str, str]) -> bool:
        """True if the cell is the only count in one of its lines: it equals that line's total."""
        return any(
            [other for other in lines[index] if count(other) > 0] == [cell]
            for index in lines_with[cell]
        )

    to_check = deque(range(len(lines)))
    while to_check:
        counted = [cell for cell in lines[to_check.popleft()] if count(cell) > 0]
        hidden_cells = [cell for cell in counted if cell[1] in hidden[cell[0]]]
        shown = [cell for cell in counted if cell[1] not in hidden[cell[0]]]
        if len(hidden_cells) != 1 or not shown:
            continue
        # A cover that is a whole line elsewhere covers nothing: that line's total gives it back.
        # When every shown count is one, the lens totals give the hidden count back whatever is
        # hidden, so the smallest is taken as before.
        useful = [cell for cell in shown if not is_whole_line(cell)]
        lens, key = min(useful or shown, key=cover_order)
        hidden[lens].add(key)
        to_check.extend(lines_with[(lens, key)])
    return hidden
