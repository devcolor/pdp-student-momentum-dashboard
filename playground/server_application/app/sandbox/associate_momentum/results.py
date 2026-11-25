"""Credit momentum on the way to an associate degree, from the normalized data model.

Everyone counted here came for an associate degree in year 1. Credits are the cohort file's credits
earned at this college in each academic year, added up from year 1. A cohort is compared at a fixed
number of years only once it has had all of them: `credit_years_observed` counts the year still
under way, which isn't a full year yet.
"""

from functools import cache
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.chat.repo import import_path
from app.sandbox.shared import ChartMeta

from .schemas import (
    MilestoneResponse,
    MilestoneRow,
    MomentumResponse,
    MomentumRow,
    NearCompleterResponse,
    NearCompleterRow,
    Split,
    Window,
)

MIN_GROUP_SIZE = 10
MAX_ROWS = 5000
TIMEOUT_SECONDS = 10.0
# The last academic year the data can see is still under way, so it doesn't count as a full year.
IN_PROGRESS_YEARS = 1
UNKNOWN = "UNKNOWN"

# A domain assumption, not in the data: an associate degree takes 60 credits. Programs vary.
ASSOCIATE_CREDITS = 60
CREDIT_MILESTONES = (15, 30, 45, ASSOCIATE_CREDITS)
# The near-completers guide's brackets: within 15 credits is about a term, within 6 is one or two
# courses.
TERM_SHORT_CREDITS = 15
COURSES_SHORT_CREDITS = 6
NEAR_COMPLETER_CREDITS = ASSOCIATE_CREDITS - TERM_SHORT_CREDITS
COURSES_SHORT_FROM = ASSOCIATE_CREDITS - COURSES_SHORT_CREDITS
# Year-1 credits earned: 12 is one full-time term, and 24 and 30 are common early-momentum marks.
YEAR_ONE_BAND_EDGES = (12, 24, 30)

# Credential Type Sought Year 1 as the data model stores it: the dictionary's code for an associate.
ASSOCIATE_SOUGHT_CODES = ("A",)

# Column names come only from these tables and the split table below, never from the request.
_EARNED_COLUMNS = (
    "number_of_credits_earned_yr_1",
    "number_of_credits_earned_yr_2",
    "number_of_credits_earned_yr_3",
    "number_of_credits_earned_yr_4",
)
_EARNED_FIELDS = (
    "Number of Credits Earned Year 1",
    "Number of Credits Earned Year 2",
    "Number of Credits Earned Year 3",
    "Number of Credits Earned Year 4",
)
_ASSOCIATE_HERE = "first_year_to_associates_at_coho"
_CREDENTIALS_ELSEWHERE = ("first_year_to_a_or_c_at_other", "first_year_to_bachelor_at_other")
_CREDENTIAL_FIELDS = [
    "First Year to Associates at Cohort Inst",
    "First Year to Associates or Certificate at Other Institution",
    "First Year to Bachelors at Other Institution",
]

_SPLIT_LABELS: dict[Split, str] = {
    "credits_short": f"Credits short of {ASSOCIATE_CREDITS}",
    "enrollment": "Enrollment here after the window",
    "intensity": "First-term intensity",
}
_SPLIT_FIELDS: dict[Split, list[str]] = {
    "credits_short": [],
    "enrollment": ["Year of Last Enrollment at Cohort Institution"],
    "intensity": ["Enrollment Intensity First Term"],
}
# The part of each split the takeaway reports on: the students an advisor would act on first.
_FOCUS_PARTS: dict[Split, str] = {
    "credits_short": "enough",
    "enrollment": "not_enrolled_after",
    "intensity": "Part-Time",
}
_ASSOCIATE_EARNED = "Earned the associate"
_NOT_RECORDED = "Not recorded"

_SEEKERS = "Students whose Credential Type Sought Year 1 is an associate degree (code A)."
_CREDITS = (
    "The cohort file's credits earned at this college, added up from year 1 to the end of year N. "
    "PDP counts every earned credit, developmental and elective courses included, so a credit "
    "total is not a degree audit: the near-completers guide rejects raw credits for this reason."
)
_ASSUMED = (
    f"An associate degree is assumed to take {ASSOCIATE_CREDITS} credits. The data doesn't say "
    "this; it's a common requirement, and programs vary."
)
_MISSING = (
    "Associate-seekers with a blank credit year inside the window are left out: for a year the "
    "data can see, a blank means the value is missing."
)
_FINDING_4 = (
    "Quality finding 4: on the mock data, year-1 credits attempted differ from the student's "
    "year-1 course rows for 1,303 students. This page reads credits earned as reported, which may "
    "share the problem, so some students may sit on the wrong side of a milestone or band edge."
)
_FINDING_N20 = (
    "Quality finding N20: on the mock data, 52 students have year-1 credits attempted below 1. "
    "This page doesn't read credits attempted and keeps them as stored; their year-1 credits "
    "earned are under 1 too, so they count in the lowest band and add nothing in year 1."
)
_WITHIN = "Within N years means by the end of the Nth academic year after entry."
_TOO_NEW = (
    "A cohort is left out until it has had N full years. The last year the data can see is still "
    "under way, so it isn't counted as a full year."
)
_SUPPRESSED = f"Groups under {MIN_GROUP_SIZE} students are not shown."


@cache
def _gap_finder() -> Any:
    """The shared gap finder's comparison module, from the repository around Playground."""
    import_path(".")
    from gap_finder import compare  # type: ignore[import-not-found]

    return compare


def _fetch(sql: str, params: list[str] | None = None) -> list[list[Any]]:
    """Run one fixed read-only query, turning any database problem into a clear 503."""
    db, _, _ = query_tool._mcp()
    try:
        result = query_tool.backend().execute(sql, params, MAX_ROWS, TIMEOUT_SECONDS)
    except (db.Unavailable, db.Failed, db.TimedOut) as exc:
        detail = f"The data model couldn't be read: {exc}. Load it from the Sandbox pipeline page."
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail) from None
    if result.truncated:
        detail = f"The query returned more than {MAX_ROWS} rows, so the counts would be incomplete."
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail)
    return result.rows


def _placeholders(count: int) -> str:
    """Query placeholders in the style the backend expects, e.g. "?, ?" for SQLite."""
    marker = "?" if query_tool.backend().param_style == "qmark" else "%s"
    return ", ".join([marker] * count)


def _percent(part: int, whole: int) -> float:
    """Part as a percent of whole, to one decimal."""
    return round(part / whole * 100, 1)


def _shown(count: int) -> int | None:
    """The count, or None when the group is too small to show."""
    return count if count >= MIN_GROUP_SIZE else None


def _visible(count: int, total: int) -> bool:
    """True when neither the group nor the rest of the total is too small to show."""
    return count >= MIN_GROUP_SIZE and total - count >= MIN_GROUP_SIZE


def _share_said(count: int, total: int) -> str:
    """A share as text, e.g. "48.9%", without letting the percent give a small group away."""
    if _visible(count, total):
        return f"{_percent(count, total)}%"
    if count < MIN_GROUP_SIZE:
        return f"fewer than {MIN_GROUP_SIZE}"
    return f"all but fewer than {MIN_GROUP_SIZE}"


def _years_text(years: int) -> str:
    """ "1 year" or "3 years"."""
    return f"{years} year{'s' if years != 1 else ''}"


def _no_cohort_yet(years: int) -> str:
    """Why there's nothing to read: no cohort has had the full years."""
    return f"No cohort has had {_years_text(years)} in full yet, so there's nothing to show."


def _full_years(years_observed: int | None) -> int | None:
    """Full academic years a cohort has had, or None when the data model doesn't say."""
    if years_observed is None:
        return None
    return max(years_observed - IN_PROGRESS_YEARS, 0)


def _cohorts(years: int) -> tuple[list[str], list[str]]:
    """Cohorts that have had `years` full years, oldest first, and the cohorts too new for it."""
    rows = _fetch(
        "SELECT cohort, MAX(credit_years_observed) FROM cohort_membership "
        "GROUP BY cohort ORDER BY cohort"
    )
    observable, too_new = [], []
    for cohort, observed in rows:
        full = _full_years(observed)
        (observable if full is not None and full >= years else too_new).append(cohort)
    return observable, too_new


def _cohort_filters(years: int, cohorts: list[str], too_new: list[str]) -> list[str]:
    """The chips that say which cohorts the chart counts and which it leaves out."""
    if not cohorts:
        return ["Came for an associate", f"No cohort has had {_years_text(years)} in full"]
    filters = ["Came for an associate", f"Within {_years_text(years)} of entry"]
    if too_new:
        filters.append(f"Too new, left out: {', '.join(too_new)}")
    return filters


def _seekers_in(cohorts: list[str]) -> tuple[str, list[str]]:
    """The WHERE clause and its values for associate-seekers in the given cohorts."""
    codes = list(ASSOCIATE_SOUGHT_CODES)
    clause = (
        f"credential_type_sought_year_1 IN ({_placeholders(len(codes))}) "
        f"AND cohort IN ({_placeholders(len(cohorts))})"
    )
    return clause, [*codes, *cohorts]


def _credits_by(years: int) -> str:
    """SQL for credits earned from year 1 to the end of year `years`."""
    return "(" + " + ".join(_EARNED_COLUMNS[:years]) + ")"


def _credits_recorded(years: int) -> str:
    """SQL that keeps students with every credit year in the window recorded."""
    return " AND ".join(f"{column} IS NOT NULL" for column in _EARNED_COLUMNS[:years])


def _earned_by(column: str, years: int) -> str:
    """SQL for "first awarded within `years` years"; a blank year counts as never."""
    return f"COALESCE({column}, 0) BETWEEN 1 AND {years}"


def _change(first: tuple[int, int], last: tuple[int, int]) -> str:
    """How a rate moved between two cohorts, or "no clear change" when chance could explain it."""
    low, high = _gap_finder().newcombe_interval(last[0], last[1], first[0], first[1])
    if low <= 0 <= high:
        return "no clear change"
    points = abs(round(_percent(*last) - _percent(*first), 1))
    return f"{'down' if high < 0 else 'up'} {points} points"


def _milestone_labels() -> list[str]:
    """Each credit milestone's name, then the associate itself, in funnel order."""
    return [f"{credits} credits" for credits in CREDIT_MILESTONES] + [_ASSOCIATE_EARNED]


def _milestone_row(cohort: str, milestone: str, reached: int, n: int) -> MilestoneRow:
    """One cohort's share reaching one milestone, or blanks when a small group would show."""
    if not _visible(reached, n):
        return MilestoneRow(
            cohort=cohort,
            milestone=milestone,
            status="suppressed",
            reached=None,
            n=_shown(n),
            rate=None,
        )
    return MilestoneRow(
        cohort=cohort,
        milestone=milestone,
        status="ok",
        reached=reached,
        n=n,
        rate=_percent(reached, n),
    )


def _milestone_takeaway(years: int, cohort: str, n: int, reached: list[int]) -> str:
    """Where the newest cohort drops off most, and how the associate compares with 60 credits."""
    *credits_reached, associates = reached
    # The first step is from everyone who came for an associate down to the first milestone.
    before = [n, *credits_reached[:-1]]
    steps = [start - end for start, end in zip(before, credits_reached, strict=True)]
    biggest = steps.index(max(steps))
    if biggest == 0:
        where = f"before reaching {CREDIT_MILESTONES[0]} credits"
    else:
        where = f"between {CREDIT_MILESTONES[biggest - 1]} and {CREDIT_MILESTONES[biggest]} credits"
    phrases = [
        f"{_share_said(count, n)} reached {credits}"
        for count, credits in zip(credits_reached, CREDIT_MILESTONES, strict=True)
    ]
    phrases[0] += " credits"
    reached_text = f"{', '.join(phrases[:-1])} and {phrases[-1]}"
    full_credits = credits_reached[-1]
    if associates > full_credits:
        compared = "more than"
    elif associates < full_credits:
        compared = "fewer than"
    else:
        compared = "as many as"
    return (
        f"Within {_years_text(years)}, associate-seekers in the {cohort} cohort drop off most "
        f"{where}: {reached_text}; {_share_said(associates, n)} earned the associate, {compared} "
        f"reached {ASSOCIATE_CREDITS} credits here."
    )


def get_milestones(window: Window) -> MilestoneResponse:
    """Per cohort, the share of associate-seekers reaching each credit milestone and the degree."""
    years = int(window)
    cohorts, too_new = _cohorts(years)
    credits = _credits_by(years)
    reached_sums = ", ".join(
        f"SUM(CASE WHEN {credits} >= {milestone} THEN 1 ELSE 0 END)"
        for milestone in CREDIT_MILESTONES
    )
    fetched = []
    if cohorts:
        where, params = _seekers_in(cohorts)
        fetched = _fetch(
            f"SELECT cohort, COUNT(*) AS n, {reached_sums}, "
            f"SUM(CASE WHEN {_earned_by(_ASSOCIATE_HERE, years)} THEN 1 ELSE 0 END) "
            f"FROM cohort_membership WHERE {where} AND {_credits_recorded(years)} "
            "GROUP BY cohort ORDER BY cohort",
            params,
        )

    labels = _milestone_labels()
    rows = []
    newest: tuple[str, int, list[int]] | None = None
    for cohort, n, *sums in fetched:
        reached = [int(count) for count in sums]
        rows += [
            _milestone_row(cohort, label, count, n)
            for label, count in zip(labels, reached, strict=True)
        ]
        if n >= MIN_GROUP_SIZE:
            newest = (cohort, n, reached)

    if not cohorts:
        takeaway = _no_cohort_yet(years)
    elif newest is None:
        takeaway = f"No cohort has {MIN_GROUP_SIZE} or more associate-seekers to show."
    else:
        takeaway = _milestone_takeaway(years, *newest)

    return MilestoneResponse(
        meta=ChartMeta(
            title=f"Credit milestones within {_years_text(years)}, among associate-seekers",
            description=(
                "The share of each cohort's associate-seekers whose credits earned here reached "
                "each milestone, next to the share who earned the associate. The chart pairs the "
                "oldest and newest cohort; the table has every cohort."
            ),
            takeaway=takeaway,
            fields_used=[
                "Cohort",
                "Credential Type Sought Year 1",
                *_EARNED_FIELDS[:years],
                _CREDENTIAL_FIELDS[0],
            ],
            filters=_cohort_filters(years, cohorts, too_new),
            definitions={
                "Associate-seekers": _SEEKERS,
                "Credits": _CREDITS,
                f"{ASSOCIATE_CREDITS} credits": _ASSUMED,
                "Left out": _MISSING,
                "Within N years": _WITHIN,
                "Too new": _TOO_NEW,
                "Finding 4": _FINDING_4,
                "<10": f"{_SUPPRESSED} A share is hidden too when fewer than "
                f"{MIN_GROUP_SIZE} students didn't reach it.",
            },
            source="synthetic",
        ),
        rows=rows,
    )


def _part_case(split: Split, years: int) -> str:
    """SQL naming each near-completer's part of the split, from fixed column names only."""
    if split == "credits_short":
        credits = _credits_by(years)
        return (
            f"CASE WHEN {credits} >= {ASSOCIATE_CREDITS} THEN 'enough' "
            f"WHEN {credits} >= {COURSES_SHORT_FROM} THEN 'courses_short' "
            "ELSE 'term_short' END"
        )
    if split == "enrollment":
        return (
            f"CASE WHEN years_of_last_enrollment_at_coho > {years} THEN 'enrolled_after' "
            "ELSE 'not_enrolled_after' END"
        )
    return f"COALESCE(enrollment_intensity_first_term, '{UNKNOWN}')"


def _part_labels(split: Split, years: int) -> dict[str, str]:
    """Each part's display name, in the order the stack is drawn from the bottom up."""
    if split == "credits_short":
        return {
            "term_short": f"{NEAR_COMPLETER_CREDITS} to under {COURSES_SHORT_FROM}: about a term "
            "short",
            "courses_short": f"{COURSES_SHORT_FROM} to under {ASSOCIATE_CREDITS}: 1 or 2 courses "
            "short",
            "enough": f"{ASSOCIATE_CREDITS} or more: enough credits, no degree",
        }
    if split == "enrollment":
        return {
            "enrolled_after": f"Enrolled here after year {years}",
            "not_enrolled_after": f"Not enrolled here after year {years}",
        }
    return {"Full-Time": "Full-time", "Part-Time": "Part-time", UNKNOWN: "Unknown"}


def _focus_phrase(split: Split, years: int) -> str:
    """What the takeaway says about the focus part, e.g. "had not enrolled here after year 3"."""
    if split == "credits_short":
        return f"already had {ASSOCIATE_CREDITS} or more credits"
    if split == "enrollment":
        return f"had not enrolled here after year {years}"
    return "started part-time"


def _hidden_parts(counts: dict[str, int]) -> set[str]:
    """Parts under the threshold, plus the smallest others until the hidden parts add up to it."""
    # The near-completers guide asks for this: with the cohort's total shown, one hidden part could
    # otherwise be worked out by subtraction. Hidden parts of zero students give nothing away.
    hidden = {part for part, count in counts.items() if count < MIN_GROUP_SIZE}
    others = sorted((part for part in counts if part not in hidden), key=lambda part: counts[part])
    while 0 < sum(counts[part] for part in hidden) < MIN_GROUP_SIZE and others:
        hidden.add(others.pop(0))
    return hidden


def _near_takeaway(
    years: int,
    split: Split,
    cohorts: list[str],
    seekers: dict[str, int],
    counts: dict[str, dict[str, int]],
    hidden: dict[str, set[str]],
) -> str:
    """The pool's share of associate-seekers, oldest against newest, and the focus part's share."""
    pools = {cohort: sum(counts.get(cohort, {}).values()) for cohort in cohorts}
    shown = [cohort for cohort in cohorts if _visible(pools[cohort], seekers.get(cohort, 0))]
    if not shown:
        return f"No cohort has {MIN_GROUP_SIZE} or more near-completers to show."
    first, last = shown[0], shown[-1]
    lead = (
        f"Within {_years_text(years)}, near-completers were "
        f"{_percent(pools[first], seekers[first])}% of associate-seekers in {first} "
        f"({pools[first]})"
    )
    if last != first:
        change = _change((pools[first], seekers[first]), (pools[last], seekers[last]))
        lead += f" and {_percent(pools[last], seekers[last])}% in {last} ({pools[last]}), {change}"

    focus = _FOCUS_PARTS[split]
    if focus in hidden[last]:
        return (
            f"{lead}; in {last}, the share who {_focus_phrase(split, years)} is hidden to keep "
            "small groups private."
        )
    focus_share = _percent(counts[last].get(focus, 0), pools[last])
    return f"{lead}; in {last}, {focus_share}% of them {_focus_phrase(split, years)}."


def get_near_completers(window: Window, split: Split) -> NearCompleterResponse:
    """Associate-seekers with most of the credits but no credential, by cohort and one split."""
    years = int(window)
    cohorts, too_new = _cohorts(years)
    credits = _credits_by(years)
    no_credential = " AND ".join(
        f"NOT {_earned_by(column, years)}" for column in (_ASSOCIATE_HERE, *_CREDENTIALS_ELSEWHERE)
    )
    near = f"{credits} >= {NEAR_COMPLETER_CREDITS} AND {no_credential}"
    fetched = []
    if cohorts:
        where, params = _seekers_in(cohorts)
        fetched = _fetch(
            f"SELECT cohort, CASE WHEN {near} THEN {_part_case(split, years)} END AS part, "
            f"COUNT(*) AS n FROM cohort_membership WHERE {where} AND {_credits_recorded(years)} "
            "GROUP BY 1, 2",
            params,
        )

    seekers: dict[str, int] = {}
    counts: dict[str, dict[str, int]] = {}
    for cohort, part, n in fetched:
        seekers[cohort] = seekers.get(cohort, 0) + n
        # A blank part is everyone who isn't a near-completer.
        if part is not None:
            in_cohort = counts.setdefault(cohort, {})
            in_cohort[part or UNKNOWN] = in_cohort.get(part or UNKNOWN, 0) + n

    labels = _part_labels(split, years)
    present = {part for in_cohort in counts.values() for part in in_cohort}
    parts = [part for part in labels if part in present] + sorted(present - set(labels))

    rows = []
    hidden: dict[str, set[str]] = {}
    for cohort in cohorts:
        in_cohort = {part: counts.get(cohort, {}).get(part, 0) for part in parts}
        pool, cohort_seekers = sum(in_cohort.values()), seekers.get(cohort, 0)
        pool_shown = _visible(pool, cohort_seekers)
        hidden[cohort] = _hidden_parts(in_cohort) if pool_shown else set(parts)
        for part in parts:
            shown = part not in hidden[cohort]
            rows.append(
                NearCompleterRow(
                    cohort=cohort,
                    part=labels.get(part, part),
                    count=in_cohort[part] if shown else None,
                    share_of_pool=_percent(in_cohort[part], pool) if shown else None,
                    pool=pool if pool_shown else None,
                    seekers=_shown(cohort_seekers),
                    pool_rate=_percent(pool, cohort_seekers) if pool_shown else None,
                )
            )

    takeaway = (
        _near_takeaway(years, split, cohorts, seekers, counts, hidden)
        if cohorts
        else _no_cohort_yet(years)
    )
    return NearCompleterResponse(
        meta=ChartMeta(
            title=(
                f"Near-completers within {_years_text(years)}, by {_SPLIT_LABELS[split].lower()}"
            ),
            description=(
                f"Associate-seekers with {NEAR_COMPLETER_CREDITS} or more credits earned here, but "
                "no associate here and no credential elsewhere. Each bar splits one cohort's "
                "near-completers into parts; the table gives the counts and the pool's size."
            ),
            takeaway=takeaway,
            fields_used=[
                "Cohort",
                "Credential Type Sought Year 1",
                *_EARNED_FIELDS[:years],
                *_CREDENTIAL_FIELDS,
                *_SPLIT_FIELDS[split],
            ],
            filters=[*_cohort_filters(years, cohorts, too_new), _SPLIT_LABELS[split]],
            definitions={
                "Near-completer": (
                    f"{NEAR_COMPLETER_CREDITS} or more credits by the end of year N, the "
                    'near-completers guide\'s "within 15 credits" of the assumed '
                    f"{ASSOCIATE_CREDITS}, and no associate here and no associate, certificate or "
                    "bachelor's elsewhere within N years. A certificate here doesn't count: it "
                    "isn't the associate they came for."
                ),
                "Credits short": (
                    f"The guide's brackets: {COURSES_SHORT_CREDITS} or fewer credits short is 1 or "
                    f"2 courses, {COURSES_SHORT_CREDITS + 1} to {TERM_SHORT_CREDITS} about a term."
                ),
                "Enrolled here after": (
                    "Year of Last Enrollment at Cohort Institution is later than year N. For the "
                    "newest cohort, the year after the window is still under way, so some who "
                    "will come back haven't yet."
                ),
                "Credits": _CREDITS,
                f"{ASSOCIATE_CREDITS} credits": _ASSUMED,
                "Left out": _MISSING,
                "Too new": _TOO_NEW,
                "<10": (
                    f"{_SUPPRESSED} When one hidden part could be worked out from the cohort's "
                    "total, the next smallest part is hidden too."
                ),
            },
            source="synthetic",
        ),
        rows=rows,
    )


def _band_labels() -> dict[str, str]:
    """Each year-1 credit band's key and name, lowest first, from the band edges."""
    low, *_, high = YEAR_ONE_BAND_EDGES
    labels = {"band_0": f"Under {low} credits"}
    edge_pairs = zip(YEAR_ONE_BAND_EDGES[:-1], YEAR_ONE_BAND_EDGES[1:], strict=True)
    for index, (start, end) in enumerate(edge_pairs):
        labels[f"band_{index + 1}"] = f"{start} to under {end} credits"
    labels[f"band_{len(YEAR_ONE_BAND_EDGES)}"] = f"{high} or more credits"
    return labels


def _band_case() -> str:
    """SQL naming each student's year-1 credit band, or UNKNOWN when year 1 wasn't recorded."""
    year_one = _EARNED_COLUMNS[0]
    steps = " ".join(
        f"WHEN {year_one} < {edge} THEN 'band_{index}'"
        for index, edge in enumerate(YEAR_ONE_BAND_EDGES)
    )
    return (
        f"CASE WHEN {year_one} IS NULL THEN '{UNKNOWN}' {steps} "
        f"ELSE 'band_{len(YEAR_ONE_BAND_EDGES)}' END"
    )


def _band_change(low: MomentumRow, high: MomentumRow) -> str:
    """ "rises from 3.9% (under 12 credits in year 1) to 61.5% (30 or more credits)", or falls."""
    start = f"{low.rate}% ({low.group.lower()} in year 1)"
    end = f"{high.rate}% ({high.group.lower()})"
    if (high.rate or 0) > (low.rate or 0):
        return f"rises from {start} to {end}"
    if (high.rate or 0) < (low.rate or 0):
        return f"falls from {start} to {end}"
    return f"is the same, {start} and {end}"


def _year_one_takeaway(years: int, cohort_label: str, rows: list[MomentumRow]) -> str:
    """How the associate rate moves from the lowest year-1 band to the highest, and the top gap."""
    bands = [row for row in rows if row.status == "ok" and row.rate is not None]
    lead = f"Among associate-seekers in the {cohort_label} cohorts"
    if len(bands) < 2:
        return f"{lead}, too few year-1 credit bands have {MIN_GROUP_SIZE} or more students."
    lead += f", the associate within {_years_text(years)} {_band_change(bands[0], bands[-1])}"
    clear = [row for row in bands if row.likely_noise is False and row.gap_pts is not None]
    if not clear:
        return f"{lead}; no band differs from everyone else by more than chance would explain."
    row = max(clear, key=lambda each: abs(each.gap_pts or 0))
    gap = round(row.gap_pts or 0, 1)
    return (
        f'{lead}; the clearest gap is "{row.group}", {row.rate}% against {row.comparison_rate}% '
        f"for everyone else ({gap:+} points)."
    )


def get_year_one(window: Window) -> MomentumResponse:
    """The associate within the window for each year-1 credit band, against everyone else."""
    years = int(window)
    cohorts, too_new = _cohorts(years)
    cohort_label = " + ".join(cohorts)
    fetched = []
    if cohorts:
        where, params = _seekers_in(cohorts)
        fetched = _fetch(
            f"SELECT {_band_case()} AS band, COUNT(*) AS n, "
            f"SUM(CASE WHEN {_earned_by(_ASSOCIATE_HERE, years)} THEN 1 ELSE 0 END) AS earned "
            f"FROM cohort_membership WHERE {where} GROUP BY 1",
            params,
        )

    gap = _gap_finder()
    labels = _band_labels()
    order = [*labels, UNKNOWN]
    measure = f"associate_within_{years}y"
    note = f"Associate within {_years_text(years)}, among associate-seekers."
    counts = {band: (n, int(earned)) for band, n, earned in fetched}
    total_n = sum(n for n, _ in counts.values())
    total_earned = sum(earned for _, earned in counts.values())

    rows: list[MomentumRow] = []
    everyone_rate = None
    if total_n:
        everyone_rate = _percent(total_earned, total_n)
        count_rows = [
            gap.CountRow(
                measure, cohort_label, (), (), total_earned, total_n, "ok", 0, 0, None, note, ""
            )
        ]
        count_rows += [
            gap.CountRow(
                measure,
                cohort_label,
                ("year_one_credits",),
                (band,),
                earned,
                n,
                "ok",
                0,
                0,
                None,
                note,
                "",
            )
            for band, (n, earned) in counts.items()
        ]
        compared = sorted(
            gap.compare(count_rows), key=lambda result: order.index(result.group_values[0])
        )
        for result in compared:
            shown = result.numerator is not None and result.denominator is not None
            band = result.group_values[0]
            rows.append(
                MomentumRow(
                    group=_NOT_RECORDED if band == UNKNOWN else labels[band],
                    status=result.status.value,
                    earned=result.numerator if shown else None,
                    n=result.denominator if shown else None,
                    rate=_percent(result.numerator, result.denominator) if shown else None,
                    comparison_rate=None
                    if result.comparison_rate is None
                    else round(result.comparison_rate * 100, 1),
                    gap_pts=result.gap_pts,
                    ci_low=result.ci_low,
                    ci_high=result.ci_high,
                    likely_noise=result.likely_noise,
                )
            )

    if not cohorts:
        takeaway = _no_cohort_yet(years)
    else:
        takeaway = _year_one_takeaway(years, cohort_label, rows)
    return MomentumResponse(
        meta=ChartMeta(
            title=f"The associate within {_years_text(years)}, by year-1 credits earned",
            description=(
                "Among associate-seekers, the share who earned the associate here, by how many "
                "credits they earned in year 1. The mark on each bar is everyone's rate."
            ),
            takeaway=takeaway,
            fields_used=[
                "Cohort",
                "Credential Type Sought Year 1",
                _EARNED_FIELDS[0],
                _CREDENTIAL_FIELDS[0],
            ],
            filters=[
                *_cohort_filters(years, cohorts, too_new),
                f"Cohorts {cohort_label}, pooled" if cohorts else "No cohorts pooled",
            ],
            definitions={
                "Bands": (
                    "Credits earned here in year 1. Each band includes its lower edge. The edges "
                    f"({', '.join(str(edge) for edge in YEAR_ONE_BAND_EDGES)}) are assumptions: "
                    "12 is one full-time term, and 24 and 30 are common early-momentum marks."
                ),
                "Gap": "The band's rate minus everyone else's, in points, from the gap finder.",
                "Likely noise": "The gap finder's q-value is 0.05 or more: the gap may be chance.",
                "Not recorded": (
                    "Year-1 credits are blank. Shown with its own rate, but not compared."
                ),
                "Finding 4": _FINDING_4,
                "Finding N20": _FINDING_N20,
                "Within N years": _WITHIN,
                "<10": _SUPPRESSED,
            },
            source="synthetic",
        ),
        rows=rows,
        everyone_rate=everyone_rate,
    )
