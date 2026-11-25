"""Associate and certificate completion from the normalized data model, made safe to display.

Every count here is a first award at this college, from the cohort file's year columns: 1 means
within the first year after entry, 0 means never. A cohort is compared at a fixed number of years
only once it has had all of them. `credit_years_observed` says how many academic years the data can
see for a cohort, and the last of those is still under way, so its awards are only partly in.
"""

from functools import cache
from typing import Any

from fastapi import HTTPException, status

from app.sandbox.chat import query_tool
from app.sandbox.chat.repo import import_path
from app.sandbox.shared import ChartMeta

from .schemas import (
    CohortRateResponse,
    CohortRateRow,
    CohortStatus,
    Credential,
    DriverResponse,
    DriverRow,
    Factor,
    FixedWindow,
    PathwayResponse,
    PathwayRow,
    ProgramResponse,
    ProgramRow,
    Window,
)

MIN_GROUP_SIZE = 10
MAX_ROWS = 5000
TIMEOUT_SECONDS = 10.0
# The year columns run from 0 to 7, so counting to 7 takes every award the data has seen.
SO_FAR_YEARS = 7
# The last academic year the data can see is still under way, so it doesn't count as a full year.
IN_PROGRESS_YEARS = 1
# Three programs plus everything else: the shared chart parts have four distinct fills.
TOP_PROGRAMS = 3
OTHER_PROGRAMS = "All other programs, or none recorded"
UNKNOWN = "UNKNOWN"

_CREDENTIAL_COLUMNS: dict[Credential, str] = {
    "associate": "first_year_to_associates_at_coho",
    "certificate": "first_year_to_certificate_at_coh",
}
_CREDENTIAL_LABELS: dict[Credential, str] = {
    "associate": "Associate degree",
    "certificate": "Certificate",
}
_A_CREDENTIAL: dict[Credential, str] = {
    "associate": "an associate degree",
    "certificate": "a certificate",
}
_CREDENTIAL_FIELDS: dict[Credential, str] = {
    "associate": "First Year to Associates at Cohort Inst",
    "certificate": "First Year to Certificate at Cohort Inst",
}
# Credential Type Sought Year 1 as the data model stores it: the dictionary's codes.
_SOUGHT_CODES: dict[Credential, tuple[str, ...]] = {
    "associate": ("A",),
    "certificate": ("C1", "C2", "C4", "01"),
}
_SEEKERS: dict[Credential, str] = {
    "associate": "associate-seekers",
    "certificate": "certificate-seekers",
}

# Column names come only from this table, never from the request.
_FACTOR_COLUMNS: dict[Factor, str] = {
    "gateway_math": "cm.completed_gateway_math_year1",
    "gateway_english": "cm.completed_gateway_english_year1",
    "enrollment_intensity": "cm.enrollment_intensity_first_term",
    "enrollment_type": "cm.enrollment_type",
    "pell": "cm.pell_status_first_year",
    "age": "s.student_age",
    "entry_term": "cm.cohort_term",
}
_FACTOR_LABELS: dict[Factor, str] = {
    "gateway_math": "Gateway math in year 1",
    "gateway_english": "Gateway English in year 1",
    "enrollment_intensity": "First-term intensity",
    "enrollment_type": "Enrollment type",
    "pell": "Pell status, first year",
    "age": "Age at entry",
    "entry_term": "Entry term",
}
_FACTOR_FIELDS: dict[Factor, str] = {
    "gateway_math": "CompletedGatewayMathYear1",
    "gateway_english": "CompletedGatewayEnglishYear1",
    "enrollment_intensity": "Enrollment Intensity First Term",
    "enrollment_type": "Enrollment Type",
    "pell": "Pell Status First Year",
    "age": "Student Age",
    "entry_term": "Cohort Term",
}
# Display names in the order the bars are drawn. Values not listed keep their stored spelling.
_VALUE_LABELS: dict[Factor, dict[str, str]] = {
    "gateway_math": {
        "C": "Finished gateway math",
        "D": "Required, didn't finish",
        "NA": "Not required",
        UNKNOWN: "Not recorded",
    },
    "gateway_english": {
        "C": "Finished gateway English",
        "D": "Required, didn't finish",
        "NA": "Not required",
        UNKNOWN: "Not recorded",
    },
    "enrollment_intensity": {
        "Full-Time": "Full-time",
        "Part-Time": "Part-time",
        UNKNOWN: "Unknown",
    },
    "enrollment_type": {
        "First-Time": "First-time",
        "Transfer-In": "Transfer-in",
        "Re-admit": "Re-admit",
    },
    "pell": {"Y": "Pell", "N": "No Pell", "U": "Code U (undefined)", UNKNOWN: "Unknown"},
    "age": {
        "20 and younger": "20 and younger",
        ">20 - 24": "Over 20, up to 24",
        "Older than 24": "Older than 24",
        UNKNOWN: "Unknown",
    },
    "entry_term": {"FALL": "Fall", "WINTER": "Winter", "SPRING": "Spring", "SUMMER": "Summer"},
}

# The first two digits of a CIP code name its family (NCES CIP 2020 series).
_CIP_FAMILIES = {
    "01": "Agriculture",
    "09": "Communication",
    "10": "Communications tech",
    "11": "Computer science",
    "12": "Personal and culinary services",
    "13": "Education",
    "14": "Engineering",
    "15": "Engineering tech",
    "19": "Family and consumer sciences",
    "22": "Legal",
    "23": "English",
    "24": "Liberal arts and general studies",
    "26": "Biology",
    "27": "Math",
    "30": "Interdisciplinary",
    "31": "Recreation and fitness",
    "40": "Physical sciences",
    "41": "Science tech",
    "42": "Psychology",
    "43": "Public safety",
    "44": "Public administration and social service",
    "45": "Social sciences",
    "46": "Construction trades",
    "47": "Mechanic and repair",
    "48": "Precision production",
    "49": "Transportation",
    "50": "Visual and performing arts",
    "51": "Health",
    "52": "Business",
    "54": "History",
}

_PATHWAYS = {
    "certificate_only": "Certificate only",
    "associate_only": "Associate only",
    "both_same_year": "Both, same year",
    "both_different_years": "Both, different years",
}
_SOUGHT_GROUPS = {
    "associate": "Associate-seekers",
    "certificate": "Certificate-seekers",
    "other": "Other or unknown goal",
}

_WITHIN = (
    "Within N years means the credential was awarded in the first N academic years after entry."
)
_SUPPRESSED = f"Groups under {MIN_GROUP_SIZE} students are not shown."
_TOO_NEW = (
    "A cohort is left out of an N-year view until it has had N full years. The last year the data "
    "can see is still under way, so it isn't counted as a full year."
)
_NO_CLEAR_CHANGE = (
    "No clear change: the 95% interval for the difference between the two cohorts includes zero."
)


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


def _said(count: int) -> str:
    """A count as text, without revealing one under the display threshold."""
    return str(count) if count >= MIN_GROUP_SIZE else f"fewer than {MIN_GROUP_SIZE}"


def _years_text(years: int) -> str:
    """ "1 year" or "3 years"."""
    return f"{years} year{'s' if years != 1 else ''}"


def _not_enough_cohorts(count: int, years: int) -> str:
    """Why there's no trend to read: too few cohorts have had the full years."""
    if count == 0:
        return f"No cohort has had {_years_text(years)} in full yet, so there's nothing to compare."
    full = _years_text(years)
    return f"Only {count} cohort has had {full} in full, so there's no trend to compare yet."


def _moved(start: float, end: float) -> str:
    """ "fall from 19.1% to 2.9%", "rise from ...", or "stay at ..."."""
    if end < start:
        return f"fall from {start}% to {end}%"
    if end > start:
        return f"rise from {start}% to {end}%"
    return f"stay at {start}%"


def _full_years(years_observed: int | None) -> int | None:
    """Full academic years a cohort has had, or None when the data model doesn't say."""
    if years_observed is None:
        return None
    return max(years_observed - IN_PROGRESS_YEARS, 0)


def _cohort_counts(years: int) -> list[tuple[str, int | None, int, int, int]]:
    """Per cohort: full years seen, students, and associates and certificates within `years`."""
    rows = _fetch(
        "SELECT cohort, MAX(credit_years_observed) AS years_observed, COUNT(*) AS n, "
        f"SUM(CASE WHEN first_year_to_associates_at_coho BETWEEN 1 AND {years} THEN 1 ELSE 0 END), "
        f"SUM(CASE WHEN first_year_to_certificate_at_coh BETWEEN 1 AND {years} THEN 1 ELSE 0 END) "
        "FROM cohort_membership GROUP BY cohort ORDER BY cohort"
    )
    return [
        (cohort, _full_years(observed), n, int(associate), int(certificate))
        for cohort, observed, n, associate, certificate in rows
    ]


def _observable_cohorts(years: int) -> list[str]:
    """Cohorts that have had at least `years` full years, oldest first."""
    return [
        cohort for cohort, full, *_ in _cohort_counts(years) if full is not None and full >= years
    ]


def _cohort_status(window: Window, full_years: int | None, n: int) -> CohortStatus:
    """Too new beats too small: a cohort that hasn't had the window has nothing to show yet."""
    if window != "so_far" and (full_years is None or full_years < int(window)):
        return "too_new"
    if n < MIN_GROUP_SIZE:
        return "suppressed"
    return "ok"


def _rate_row(
    cohort: str,
    full_years: int | None,
    credential: Credential,
    row_status: CohortStatus,
    earned: int,
    n: int,
) -> CohortRateRow:
    """One cohort's rate with its 95% Wilson interval, or blanks when it can't be shown."""
    if row_status != "ok":
        return CohortRateRow(
            cohort=cohort,
            full_years_seen=full_years,
            credential=_CREDENTIAL_LABELS[credential],
            status=row_status,
            earned=None,
            n=None if row_status == "suppressed" else n,
            rate=None,
            ci_low=None,
            ci_high=None,
        )
    low, high = _gap_finder().wilson_interval(earned, n)
    return CohortRateRow(
        cohort=cohort,
        full_years_seen=full_years,
        credential=_CREDENTIAL_LABELS[credential],
        status=row_status,
        earned=earned,
        n=n,
        rate=_percent(earned, n),
        ci_low=round(low * 100, 1),
        ci_high=round(high * 100, 1),
    )


def _change_phrase(first: CohortRateRow, last: CohortRateRow) -> str:
    """How a rate moved from the oldest to the newest comparable cohort, and whether it's clear."""
    if first.earned is None or first.n is None or last.earned is None or last.n is None:
        raise ValueError("only shown rows can be compared")
    low, high = _gap_finder().newcombe_interval(last.earned, last.n, first.earned, first.n)
    moved = f"{first.rate}% ({first.cohort}) to {last.rate}% ({last.cohort})"
    if low <= 0 <= high:
        return f"{moved}, no clear change"
    direction = "down" if high < 0 else "up"
    return f"{moved}, {direction} {abs(round((last.rate or 0) - (first.rate or 0), 1))} points"


def _so_far_takeaway(counts: list[tuple[str, int | None, int, int, int]]) -> str | None:
    """The trap: with no time limit, newer cohorts look worse because they've had less time."""
    shown = [row for row in counts if row[2] >= MIN_GROUP_SIZE]
    if len(shown) < 2:
        return None
    (old, _, old_n, old_assoc, old_cert), (new, new_years, new_n, new_assoc, new_cert) = (
        shown[0],
        shown[-1],
    )
    if old_assoc + old_cert == 0 or new_assoc + new_cert == 0:
        return None
    associates = _moved(_percent(old_assoc, old_n), _percent(new_assoc, new_n))
    certificate_share = _moved(
        _percent(old_cert, old_assoc + old_cert), _percent(new_cert, new_assoc + new_cert)
    )
    years_note = (
        "" if new_years is None else f" The {new} cohort has had {_years_text(new_years)} in full."
    )
    return (
        f"Counted with no time limit, associates {associates} from the {old} cohort to {new}, and "
        f"certificates {certificate_share} of credentials earned.{years_note} An associate takes "
        "two or more years, so this view mixes time with trend: pick a fixed number of years to "
        "compare fairly."
    )


def _window_takeaway(window: FixedWindow, rows: list[CohortRateRow]) -> str:
    """Compare the oldest and newest cohorts that have both had the window."""
    years = int(window)
    phrases = []
    for credential, plural_label in (("associate", "Associates"), ("certificate", "Certificates")):
        label = _CREDENTIAL_LABELS[credential]
        comparable = [row for row in rows if row.credential == label and row.status == "ok"]
        if len(comparable) < 2:
            return _not_enough_cohorts(len(comparable), years)
        phrases.append(f"{plural_label}: {_change_phrase(comparable[0], comparable[-1])}.")
    lead = f"Within {_years_text(years)}, counting only cohorts that have had them."
    return " ".join([lead, *phrases])


def get_by_cohort(window: Window) -> CohortRateResponse:
    """Associate and certificate rates per cohort, with each cohort's full years seen."""
    years = SO_FAR_YEARS if window == "so_far" else int(window)
    counts = _cohort_counts(years)
    rows = []
    for cohort, full_years, n, associate, certificate in counts:
        row_status = _cohort_status(window, full_years, n)
        rows.append(_rate_row(cohort, full_years, "associate", row_status, associate, n))
        rows.append(_rate_row(cohort, full_years, "certificate", row_status, certificate, n))

    if window == "so_far":
        title = "Credentials earned so far, by entering cohort"
        takeaway = _so_far_takeaway(counts)
        filters = ["Counted with no time limit"]
    else:
        title = f"Credentials earned within {_years_text(years)}, by entering cohort"
        takeaway = _window_takeaway(window, rows)
        filters = [
            f"Within {_years_text(years)} of entry",
            "Cohorts without the full years are left out",
        ]

    return CohortRateResponse(
        meta=ChartMeta(
            title=title,
            description=(
                "Share of each entering cohort who earned an associate degree or a certificate "
                "at this college."
            ),
            takeaway=takeaway,
            fields_used=[
                "Cohort",
                _CREDENTIAL_FIELDS["associate"],
                _CREDENTIAL_FIELDS["certificate"],
            ],
            filters=filters,
            definitions={
                "Rate": "Students who earned the credential, over every student in the cohort.",
                "Interval": "The 95% Wilson score interval for the rate, from the gap finder.",
                "Within N years": _WITHIN,
                "Too new": _TOO_NEW,
                "Change": _NO_CLEAR_CHANGE,
            },
            source="synthetic",
        ),
        rows=rows,
    )


def _program_label(code: str) -> str:
    """A six-digit CIP code as "52.0411 Business"."""
    family = _CIP_FAMILIES.get(code[:2])
    dotted = f"{code[:2]}.{code[2:]}" if len(code) == 6 else code
    return f"{dotted} {family}" if family else dotted


def _program_takeaway(
    credential: Credential,
    years: int,
    cohorts: list[str],
    counts: dict[tuple[str, str], int],
    top: list[str],
) -> str | None:
    """The top program whose earners changed most between the oldest and newest cohorts."""
    if len(cohorts) < 2:
        return _not_enough_cohorts(len(cohorts), years)
    first, last = cohorts[0], cohorts[-1]
    if not top:
        return None
    program = max(
        top, key=lambda code: abs(counts.get((last, code), 0) - counts.get((first, code), 0))
    )
    start, end = counts.get((first, program), 0), counts.get((last, program), 0)
    return (
        f"Program {_program_label(program)} changed the most: {_said(start)} students in the "
        f"{first} cohort earned {_A_CREDENTIAL[credential]} within {_years_text(years)}, and "
        f"{_said(end)} in {last}. One program opening, closing or growing can look like a "
        "college-wide trend."
    )


def get_by_program(credential: Credential, window: FixedWindow) -> ProgramResponse:
    """Earners per cohort, split into the largest programs and everything else."""
    years = int(window)
    column = _CREDENTIAL_COLUMNS[credential]
    cohorts = _observable_cohorts(years)
    fetched = _fetch(
        "SELECT cohort, COALESCE(program_of_study_year_1, '') AS program, COUNT(*) AS n "
        f"FROM cohort_membership WHERE {column} BETWEEN 1 AND {years} GROUP BY 1, 2"
    )
    counts = {(cohort, program): n for cohort, program, n in fetched if cohort in cohorts}

    totals: dict[str, int] = {}
    for (_, program), n in counts.items():
        totals[program] = totals.get(program, 0) + n
    named = [program for program in totals if program not in ("", UNKNOWN)]
    top = sorted(named, key=lambda program: (-totals[program], program))[:TOP_PROGRAMS]

    rows = []
    for cohort in cohorts:
        in_cohort = {program: n for (each, program), n in counts.items() if each == cohort}
        cohort_earned = sum(in_cohort.values())
        buckets = [(_program_label(program), in_cohort.get(program, 0)) for program in top]
        rest = sum(n for program, n in in_cohort.items() if program not in top)
        buckets.append((OTHER_PROGRAMS, rest))
        rows += [
            ProgramRow(
                cohort=cohort, program=label, earned=_shown(n), cohort_earned=_shown(cohort_earned)
            )
            for label, n in buckets
        ]

    return ProgramResponse(
        meta=ChartMeta(
            title=f"Who earned {_A_CREDENTIAL[credential]} within {_years_text(years)}, by program",
            description=(
                f"Students in each cohort who earned {_A_CREDENTIAL[credential]}, split into the "
                f"{TOP_PROGRAMS} largest programs and everything else."
            ),
            takeaway=_program_takeaway(credential, years, cohorts, counts, top),
            fields_used=["Cohort", "Program of Study Year 1", _CREDENTIAL_FIELDS[credential]],
            filters=[_CREDENTIAL_LABELS[credential], f"Within {_years_text(years)} of entry"],
            definitions={
                "Program": "The program of study at the end of year 1 (six-digit CIP code).",
                "Largest programs": f"The {TOP_PROGRAMS} with the most earners in these cohorts.",
                "Within N years": _WITHIN,
                "Too new": _TOO_NEW,
                "<10": _SUPPRESSED,
            },
            source="synthetic",
        ),
        rows=rows,
    )


def _value_order(factor: Factor, value: str) -> tuple[int, str]:
    """Listed values in their listed order, then the rest by name, unknown last."""
    listed = list(_VALUE_LABELS[factor])
    if value == UNKNOWN:
        return (len(listed) + 1, value)
    return (listed.index(value), value) if value in listed else (len(listed), value)


def _driver_takeaway(
    credential: Credential, years: int, factor: Factor, rows: list[DriverRow], cohort_label: str
) -> str:
    """The clearest gap: the group furthest from everyone else, if any gap is more than noise."""
    clear = [
        row
        for row in rows
        if row.status == "ok" and row.likely_noise is False and row.gap_pts is not None
    ]
    if not clear:
        return (
            f"Among {_SEEKERS[credential]}, no {_FACTOR_LABELS[factor].lower()} group differs from "
            "everyone else by more than chance would explain."
        )
    row = max(clear, key=lambda each: abs(each.gap_pts or 0))
    return (
        f'Among {_SEEKERS[credential]} in the {cohort_label} cohorts, the "{row.group}" group '
        f"earned {_A_CREDENTIAL[credential]} within {_years_text(years)} {row.rate}% of the time, "
        "against "
        f"{row.comparison_rate}% for everyone else ({round(row.gap_pts or 0, 1):+} points)."
    )


def get_drivers(credential: Credential, window: FixedWindow, factor: Factor) -> DriverResponse:
    """Completion within the window for each group of one factor, against everyone else."""
    years = int(window)
    cohorts = _observable_cohorts(years)
    cohort_label = " + ".join(cohorts)
    column = _CREDENTIAL_COLUMNS[credential]
    codes = list(_SOUGHT_CODES[credential])
    join = "JOIN student s ON s.student_id = cm.student_id" if factor == "age" else ""
    fetched = (
        _fetch(
            f"SELECT COALESCE({_FACTOR_COLUMNS[factor]}, '{UNKNOWN}') AS value, COUNT(*) AS n, "
            f"SUM(CASE WHEN cm.{column} BETWEEN 1 AND {years} THEN 1 ELSE 0 END) AS earned "
            f"FROM cohort_membership cm {join} "
            f"WHERE cm.cohort IN ({_placeholders(len(cohorts))}) "
            f"AND cm.credential_type_sought_year_1 IN ({_placeholders(len(codes))}) GROUP BY 1",
            [*cohorts, *codes],
        )
        if cohorts
        else []
    )

    gap = _gap_finder()
    measure = f"{credential}_within_{years}y"
    label, seekers = _CREDENTIAL_LABELS[credential], _SEEKERS[credential]
    note = f"{label} within {_years_text(years)}, among {seekers}."
    counts: dict[str, tuple[int, int]] = {}
    for value, n, earned in fetched:
        key = value or UNKNOWN
        prior_n, prior_earned = counts.get(key, (0, 0))
        counts[key] = (prior_n + n, prior_earned + int(earned))
    total_n = sum(n for n, _ in counts.values())
    total_earned = sum(earned for _, earned in counts.values())

    rows: list[DriverRow] = []
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
                measure, cohort_label, (factor,), (value,), earned, n, "ok", 0, 0, None, note, ""
            )
            for value, (n, earned) in counts.items()
        ]
        compared = sorted(
            gap.compare(count_rows), key=lambda result: _value_order(factor, result.group_values[0])
        )
        for result in compared:
            shown = result.numerator is not None and result.denominator is not None
            rows.append(
                DriverRow(
                    group=_VALUE_LABELS[factor].get(result.group_values[0], result.group_values[0]),
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
        takeaway = _not_enough_cohorts(0, years)
    else:
        takeaway = _driver_takeaway(credential, years, factor, rows, cohort_label)
    return DriverResponse(
        meta=ChartMeta(
            title=(
                f"Who finishes: {_CREDENTIAL_LABELS[credential].lower()} within "
                f"{_years_text(years)}, by {_FACTOR_LABELS[factor].lower()}"
            ),
            description=(
                f"Among students who came for {_A_CREDENTIAL[credential]} in year 1, the share who "
                "earned it, by group. The mark on each bar is everyone's rate."
            ),
            takeaway=takeaway,
            fields_used=[
                "Cohort",
                "Credential Type Sought Year 1",
                _CREDENTIAL_FIELDS[credential],
                _FACTOR_FIELDS[factor],
            ],
            filters=[
                f"Came for {_A_CREDENTIAL[credential]}",
                f"Within {_years_text(years)} of entry",
                f"Cohorts {cohort_label}, pooled" if cohorts else "No cohort has the full years",
            ],
            definitions={
                "Gap": "The group's rate minus everyone else's, in points, from the gap finder.",
                "Likely noise": "The gap finder's q-value is 0.05 or more: the gap may be chance.",
                "Within N years": _WITHIN,
                "<10": _SUPPRESSED,
            },
            source="synthetic",
        ),
        rows=rows,
        everyone_rate=everyone_rate,
    )


def _pathway_takeaway(counts: dict[tuple[str, str], int], years: int) -> str | None:
    """How often students who came for an associate left with a certificate too, or instead."""
    came_for_associate = {pathway: counts.get(("associate", pathway), 0) for pathway in _PATHWAYS}
    total = sum(came_for_associate.values())
    if total < MIN_GROUP_SIZE:
        return None
    alongside = came_for_associate["both_same_year"] + came_for_associate["both_different_years"]
    instead = came_for_associate["certificate_only"]

    def share(count: int) -> str:
        """A share of the total, or "fewer than 10" so a percent can't give a hidden count away."""
        return f"{_percent(count, total)}%" if count >= MIN_GROUP_SIZE else _said(count)

    return (
        f"Of the {total} students who came for an associate and earned a credential within "
        f"{_years_text(years)}, {share(alongside)} earned a certificate alongside the associate "
        f"and {share(instead)} earned a certificate instead of it."
    )


def get_pathways(window: FixedWindow) -> PathwayResponse:
    """For credential earners within the window: associate, certificate or both, by goal."""
    years = int(window)
    cohorts = _observable_cohorts(years)
    cohort_label = " + ".join(cohorts)
    associate, certificate = _CREDENTIAL_COLUMNS["associate"], _CREDENTIAL_COLUMNS["certificate"]
    associate_codes, certificate_codes = _SOUGHT_CODES["associate"], _SOUGHT_CODES["certificate"]
    earned_associate = f"{associate} BETWEEN 1 AND {years}"
    earned_certificate = f"{certificate} BETWEEN 1 AND {years}"
    sought_case = (
        f"CASE WHEN credential_type_sought_year_1 IN ({_placeholders(len(associate_codes))}) "
        "THEN 'associate' "
        f"WHEN credential_type_sought_year_1 IN ({_placeholders(len(certificate_codes))}) "
        "THEN 'certificate' ELSE 'other' END"
    )
    pathway_case = (
        f"CASE WHEN {earned_associate} AND {earned_certificate} THEN "
        f"CASE WHEN {associate} = {certificate} THEN 'both_same_year' "
        "ELSE 'both_different_years' END "
        f"WHEN {earned_associate} THEN 'associate_only' ELSE 'certificate_only' END"
    )
    fetched = (
        _fetch(
            f"SELECT {sought_case} AS sought, {pathway_case} AS pathway, COUNT(*) AS n "
            f"FROM cohort_membership WHERE cohort IN ({_placeholders(len(cohorts))}) "
            f"AND ({earned_associate} OR {earned_certificate}) GROUP BY 1, 2",
            [*associate_codes, *certificate_codes, *cohorts],
        )
        if cohorts
        else []
    )
    counts = {(sought, pathway): n for sought, pathway, n in fetched}

    rows = []
    for sought, sought_label in _SOUGHT_GROUPS.items():
        sought_total = sum(counts.get((sought, pathway), 0) for pathway in _PATHWAYS)
        if sought_total == 0:
            continue
        for pathway, pathway_label in _PATHWAYS.items():
            # A small group hides its total too, or the total would give its parts away.
            shown = (
                _shown(counts.get((sought, pathway), 0)) if sought_total >= MIN_GROUP_SIZE else None
            )
            rows.append(
                PathwayRow(
                    sought=sought_label,
                    pathway=pathway_label,
                    n=shown,
                    share=None if shown is None else _percent(shown, sought_total),
                    sought_total=_shown(sought_total),
                )
            )

    return PathwayResponse(
        meta=ChartMeta(
            title=f"Associate, certificate or both, within {_years_text(years)}",
            description=(
                "Students who earned a credential at this college, by what they came for and what "
                "they earned."
            ),
            takeaway=_pathway_takeaway(counts, years) if cohorts else _not_enough_cohorts(0, years),
            fields_used=[
                "Cohort",
                "Credential Type Sought Year 1",
                _CREDENTIAL_FIELDS["associate"],
                _CREDENTIAL_FIELDS["certificate"],
            ],
            filters=[
                f"Within {_years_text(years)} of entry",
                f"Cohorts {cohort_label}, pooled" if cohorts else "No cohort has the full years",
            ],
            definitions={
                "Both, same year": "Associate and certificate first awarded in the same year after "
                "entry, often a certificate built into the degree.",
                "Both, different years": "One credential first, the other in a later year.",
                "Came for": "Credential Type Sought Year 1. Certificates are the under-one-year, "
                "one-to-two-year, two-to-four-year and undergraduate certificate codes.",
                "<10": _SUPPRESSED,
            },
            source="synthetic",
        ),
        rows=rows,
    )
