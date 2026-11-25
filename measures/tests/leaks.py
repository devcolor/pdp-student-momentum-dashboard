"""Works out what subtraction gives away from a run's rows, for the hiding tests."""
import random
from collections import defaultdict
from itertools import combinations

from measures.models import SUPPRESSION_THRESHOLD, Cohort, Group, GroupDimension
from measures.run_measures import ACROSS_NOTE, COMPLEMENT_NOTE, is_counted, line_total, lines_by_key


def lines_and_totals(rows: dict) -> list[tuple[list, tuple | None]]:
    """Each line's (cohort, group) rows, with the row among them that the others add up to, or None.

    The lines are each cohort's own (lines_by_key), where a deeper total is one of the line's rows, then each
    pool's line per group when the rows hold it in all its years, where the pool's row is the total. An everyone
    or one-way total, such as a rectangle's course, is taken as published, so it isn't a row of its line.
    """
    own, _ = lines_by_key(rows)
    lines = []
    for key, groups in own.items():
        line = [(key[0], group) for group in groups]
        total = (key[0], line_total(key))
        lines.append((line, total if total in line else None))
    cohorts = {cohort for cohort, _ in rows}
    for cohort, group in rows:
        years = [Cohort.of(year) for year in sorted(cohort.years)]
        line = [(cohort, group), *((year, group) for year in years)]
        if len(years) > 1 and all(year in cohorts for year in years) and group.parts and all(key in rows for key in line):
            lines.append((line, (cohort, group)))
    return lines


def every_line(rows: dict) -> list[list]:
    """Each line's rows, as lines_and_totals gives them."""
    return [line for line, _ in lines_and_totals(rows)]


def worked_out(results: list, all_counts: dict) -> list:
    """The (cohort, group) rows hidden for their size whose counts subtraction gives back, line by line.

    A line with one hidden row anyone is counted in gives that row away, which can leave another line with one,
    so this repeats until nothing more comes out. Rows hidden only as cover may come out; the small ones mustn't.
    recoverable also finds what only several lines together give.
    """
    rows = {(r.cohort, r.group): r for r in results}
    lines = every_line(rows)
    known = set()

    def unknown(key) -> bool:
        """Hidden, counting someone, and not yet given away."""
        return rows[key].suppressed and all_counts[key].denominator > 0 and key not in known

    found = True
    while found:
        found = False
        for line in lines:
            hidden = [key for key in line if unknown(key)]
            if len(hidden) == 1:
                known.add(hidden[0])
                found = True
    return sorted(((c.label, g.label) for c, g in known if all_counts[(c, g)].n_students < SUPPRESSION_THRESHOLD))


def weak_covers(results: list, all_counts: dict) -> list:
    """The (cohort, group) rows hidden as cover that cover nothing, because they equal a total a reader can see.

    A cover is weak when nobody else is counted in one of its lines: it then equals that line's total, which is
    taken as published when it isn't a row of the line, and is seen when it's a shown row of the line.
    """
    rows = {(r.cohort, r.group): r for r in results}
    lines_of = defaultdict(list)
    for line, total in lines_and_totals(rows):
        for key in line:
            if key != total:
                lines_of[key].append((line, total))

    weak = []
    for key, row in rows.items():
        # The noise note can follow the cover's note, so look for it anywhere in the note.
        if COMPLEMENT_NOTE not in row.note and ACROSS_NOTE not in row.note:
            continue
        for line, total in lines_of[key]:
            others = [other for other in line if other not in (key, total) and all_counts[other].denominator > 0]
            if not others and (total is None or not rows[total].suppressed):
                weak.append((key[0].label, key[1].label))
                break
    return sorted(weak)


# Sums are worked modulo this prime, which stands in for exact arithmetic: every coefficient is 1 or -1.
PRIME = 2_147_483_647


def recoverable(results: list, all_counts: dict, seed: int = 1, totals_published: bool = True) -> list:
    """The (cohort, group) rows hidden for their size whose exact counts some sum of the rows gives back.

    worked_out peels one line at a time; this solves every relation together, so it also finds what only several
    lines give, such as a course minus two of its rows plus a third. A hidden group is given back when it is 0 in
    every solution of the relations with the known counts set to 0. One random solution modulo PRIME tells which:
    a group that isn't given back is 0 in it with a chance of about one in two billion. With totals_published False,
    totals outside the rows given aren't known (see is_known).
    """
    rows = {(r.cohort, r.group): r for r in results}
    groups = every_group(rows)
    unknown = sorted((key for key in groups if not is_known(key, rows, all_counts, totals_published)), key=label_of)
    solution = random_solution(relations(groups, set(unknown)), unknown, random.Random(seed))
    found = [key for key in unknown if key in rows and solution[key] == 0]
    return sorted(label_of(key) for key in found if all_counts[key].n_students < SUPPRESSION_THRESHOLD)


def label_of(key: tuple) -> tuple:
    """A (cohort, group) key as (cohort label, group label), to sort and report by."""
    return key[0].label, key[1].label


def every_group(rows: dict) -> set:
    """Each row's (cohort, group), and every coarser group it adds up into, such as course x race from a course x race x gender row."""
    groups = set()
    for cohort, group in rows:
        for size in range(len(group.parts) + 1):
            for parts in combinations(group.parts, size):
                groups.add((cohort, Group(frozenset(parts))))
    return groups


def is_known(key: tuple, rows: dict, all_counts: dict, totals_published: bool = True) -> bool:
    """Whether a reader has the group's counts: it's shown, nobody is counted in it, or it's a one-way total taken as published."""
    if key in all_counts and not is_counted(all_counts[key]):
        return True
    if key in rows:
        return not rows[key].suppressed
    # Not among the rows: hiding takes everyone and one-way totals as published, and nothing deeper. With
    # totals_published False they're unknown: the manifest runs each measure and cohort once, so a total outside
    # the run is published nowhere.
    return totals_published and len(key[1].parts) <= 1


def relations(groups: set, unknown: set) -> list[dict]:
    """Each sum that holds among the groups, as {unknown group: coefficient}; the known groups' counts drop out.

    A group is the sum of the groups that split it by one more dimension, and a pool's group is the sum of the
    same group in each of its years.
    """
    splits = defaultdict(list)  # (cohort, total, dimension) -> the groups that split the total by that dimension
    for cohort, group in groups:
        for part in group.parts:
            splits[(cohort, Group(group.parts - {part}), part.dimension)].append((cohort, group))
    sums = [((cohort, total), members) for (cohort, total, _), members in splits.items()]
    cohorts = {cohort for cohort, _ in groups}
    for pool in cohorts:
        years = [Cohort.of(year) for year in sorted(pool.years)]
        if len(years) < 2 or any(year not in cohorts for year in years):
            continue
        for cohort, group in groups:
            members = [(year, group) for year in years]
            if cohort == pool and all(member in groups for member in members):
                sums.append(((pool, group), members))

    equations = []
    for total, members in sums:
        equation = {member: 1 for member in members if member in unknown}
        if total in unknown:
            equation[total] = PRIME - 1
        if equation:
            equations.append(equation)
    return equations


def course_of(key: tuple):
    """The (cohort, course) a group holds, or None for a group across courses."""
    for part in key[1].parts:
        if part.dimension == GroupDimension.COURSE:
            return key[0], part.value
    return None


def random_solution(equations: list[dict], unknown: list, rng: random.Random) -> dict:
    """One random solution, by group, of equations that each add up to 0 modulo PRIME.

    Each course's own equations hold few groups, so they're solved one course at a time first. The equations
    across courses are then solved in terms of what each course leaves free.
    """
    within, across = defaultdict(list), []
    for equation in equations:
        places = {course_of(key) for key in equation}
        if len(places) == 1 and None not in places:
            within[places.pop()].append(equation)
        else:
            across.append(equation)
    by_place = defaultdict(list)
    for key in unknown:
        by_place[course_of(key)].append(key)

    # Every solution within the courses is a weighted sum of these vectors, each {group: value}.
    vectors = []
    for place, keys in by_place.items():
        if place is None:
            vectors.extend({key: 1} for key in keys)
        else:
            vectors.extend(null_space(within[place], keys))
    in_vectors = defaultdict(list)  # group -> (vector index, its value there)
    for index, vector in enumerate(vectors):
        for key, value in vector.items():
            in_vectors[key].append((index, value))

    # The equations across courses, rewritten as equations on the weights.
    weight_equations = []
    for equation in across:
        on_weights = defaultdict(int)
        for key, coefficient in equation.items():
            for index, value in in_vectors[key]:
                on_weights[index] = (on_weights[index] + coefficient * value) % PRIME
        weight_equations.append(on_weights)
    weights = random_null_vector(weight_equations, len(vectors), rng)

    solution = defaultdict(int)
    for index, vector in enumerate(vectors):
        for key, value in vector.items():
            solution[key] = (solution[key] + weights[index] * value) % PRIME
    return solution


def null_space(equations: list[dict], keys: list) -> list[dict]:
    """Vectors, each {group: value}, whose weighted sums are every solution of equations over these groups."""
    column = {key: index for index, key in enumerate(keys)}
    matrix = [[0] * len(keys) for _ in equations]
    for row, equation in enumerate(equations):
        for key, coefficient in equation.items():
            matrix[row][column[key]] = coefficient % PRIME
    pivots = row_reduce(matrix, len(keys))
    vectors = []
    for free in sorted(set(range(len(keys))) - set(pivots)):
        vector = {keys[free]: 1}
        for row, pivot in enumerate(pivots):
            if matrix[row][free]:
                vector[keys[pivot]] = -matrix[row][free] % PRIME
        vectors.append(vector)
    return vectors


def random_null_vector(equations: list[dict], size: int, rng: random.Random) -> list[int]:
    """size random values, modulo PRIME, that solve equations given as {index: coefficient}."""
    values = [rng.randrange(PRIME) for _ in range(size)]
    # Only the columns the equations touch need row reducing; the rest stay random.
    columns = sorted({index for equation in equations for index, coefficient in equation.items() if coefficient})
    position = {index: place for place, index in enumerate(columns)}
    matrix = [[0] * len(columns) for _ in equations]
    for row, equation in enumerate(equations):
        for index, coefficient in equation.items():
            if coefficient:
                matrix[row][position[index]] = coefficient
    pivots = row_reduce(matrix, len(columns))
    for row, pivot in enumerate(pivots):
        rest = sum(matrix[row][place] * values[columns[place]] for place in range(len(columns)) if place != pivot)
        values[columns[pivot]] = -rest % PRIME
    return values


def row_reduce(matrix: list[list[int]], width: int) -> list[int]:
    """Bring matrix to reduced row echelon form modulo PRIME, in place. Returns each pivot row's column."""
    pivots = []
    for col in range(width):
        row = len(pivots)
        if row == len(matrix):
            break
        found = next((r for r in range(row, len(matrix)) if matrix[r][col]), None)
        if found is None:
            continue
        matrix[row], matrix[found] = matrix[found], matrix[row]
        inverse = pow(matrix[row][col], PRIME - 2, PRIME)
        matrix[row] = [value * inverse % PRIME for value in matrix[row]]
        for other in range(len(matrix)):
            factor = matrix[other][col]
            if other != row and factor:
                matrix[other] = [(a - factor * b) % PRIME for a, b in zip(matrix[other], matrix[row])]
        pivots.append(col)
    return pivots
