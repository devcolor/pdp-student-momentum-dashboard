"""Turn an institution's supplemental CSV into rows the data model's student_attribute table takes.

The institution's file is wide and easy to make: Student_GUID, optionally Academic_Year and
Academic_Term, then any value columns, such as Home_Zip or Advisor_Assigned. Each value column
becomes an attribute: one row per student (and term), name and value, in the long shape
config/supplemental_mapping.yaml (or supplemental_term_mapping.yaml) maps. Rows whose student isn't
in the loaded cohort file are held back by the loader and counted in its report.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

ID_COLUMN = "Student_GUID"
YEAR_COLUMN = "Academic_Year"
TERM_COLUMN = "Academic_Term"
LONG_COLUMNS = [ID_COLUMN, YEAR_COLUMN, TERM_COLUMN, "Attribute_Key", "Attribute_Value", "Source"]
MAPPING = "supplemental_mapping.yaml"
TERM_MAPPING = "supplemental_term_mapping.yaml"

_STUDENT_ID = re.compile(r"^[0-9A-Fa-f]{32}$")
_YEAR = re.compile(r"^\d{4}-\d{2}$")
_TERMS = {"FALL", "SPRING", "SUMMER", "WINTER"}
# Columns that would name a person: never part of a supplemental file.
_IDENTITY = re.compile(
    r"(^|_)(first|last|middle|full|given|family)_?name$|^name$|ssn|social_security|itin|"
    r"street|address|e_?mail|phone|birth|^dob$"
)
# Attributes the repo's own enrichment files already write. A second source of one would double
# count students in the charts that read it, so an upload can't use these names.
RESERVED_KEYS = {"affinity", "home_state", "unmet_need_band", "uses_on_campus_housing"}


class SupplementalError(Exception):
    """The file can't be used; the message says why, in words the uploader can act on."""


def source_tag(filename: str, uploaded_on: str, upload_id: str) -> str:
    """What every value of an upload records as its source: unique to the upload, so removing one
    upload removes only its values, e.g. "uploaded: aid.csv, 2026-11-10, 3f2a9c1b7d4e"."""
    return f"uploaded: {filename}, {uploaded_on}, {upload_id[:12]}"


@dataclass
class Converted:
    """What the conversion found: the counts the upload screen shows."""

    rows_read: int = 0
    facts: int = 0
    rows_set_aside: int = 0
    attributes: list[str] = field(default_factory=list)
    per_term: bool = False


def attribute_key(column: str) -> str:
    """A column name as an attribute name: "Home ZIP" becomes "home_zip"."""
    return re.sub(r"[^a-z0-9]+", "_", column.strip().lower()).strip("_")


def convert(source: Path, target: Path, origin: str) -> Converted:
    """Check the institution's file and write it to target in the long shape, or raise why not."""
    try:
        with open(source, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = [column.strip() for column in next(reader, [])]
            rows = list(reader)
    except UnicodeDecodeError as error:
        raise SupplementalError(f"The file isn't UTF-8 text: {error}") from error

    id_at, year_at, term_at, values = _read_header(header)
    per_term = year_at is not None

    result = Converted(
        rows_read=len(rows), per_term=per_term, attributes=[key for _, key in values]
    )
    seen: set[tuple[str, ...]] = set()
    with open(target, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(LONG_COLUMNS)
        for row in rows:
            cells = [*row, *[""] * (len(header) - len(row))]
            student = cells[id_at].strip()
            year = cells[year_at].strip() if year_at is not None else ""
            term = cells[term_at].strip().upper() if term_at is not None else ""
            if not _STUDENT_ID.match(student) or (
                per_term and not (_YEAR.match(year) and term in _TERMS)
            ):
                result.rows_set_aside += 1
                continue
            for at, key in values:
                value = cells[at].strip()
                fact = (student, year, term, key, value)
                if (
                    value and fact not in seen
                ):  # a blank cell is no fact; a repeated one is one fact
                    seen.add(fact)
                    writer.writerow([*fact, origin])
                    result.facts += 1
    if result.facts == 0:
        raise SupplementalError(
            "No usable rows: each needs a 32-character Student_GUID"
            + (
                ", an Academic_Year like 2024-25 and a term (FALL, SPRING, SUMMER or WINTER)"
                if per_term
                else ""
            )
            + ", and at least one filled value."
        )
    return result


def _read_header(header: list[str]) -> tuple[int, int | None, int | None, list[tuple[int, str]]]:
    """(ID column, year column, term column, [(value column, attribute name)]), or raise why not."""
    lowered = [column.lower() for column in header]
    if ID_COLUMN.lower() not in lowered:
        raise SupplementalError(
            f"The file needs a {ID_COLUMN} column: the student ID the PDP files use, which links "
            "each row to a student."
        )
    has_year, has_term = YEAR_COLUMN.lower() in lowered, TERM_COLUMN.lower() in lowered
    if has_year != has_term:
        raise SupplementalError(
            f"Give both {YEAR_COLUMN} and {TERM_COLUMN} for data per term, or neither for data "
            "about a student overall."
        )
    key_columns = {ID_COLUMN.lower(), YEAR_COLUMN.lower(), TERM_COLUMN.lower(), "source"}
    values = [
        (at, attribute_key(column))
        for at, column in enumerate(header)
        if lowered[at] not in key_columns
    ]
    if not values:
        raise SupplementalError(f"The file has no value columns besides {ID_COLUMN}.")

    keys = [key for _, key in values]
    problems = []
    if identity := [header[at] for at, key in values if _IDENTITY.search(key)]:
        problems.append(f"remove columns that name a person: {', '.join(identity)}")
    if blank := [header[at] or "(blank)" for at, key in values if not key]:
        problems.append(f"give these columns a name: {', '.join(blank)}")
    if repeated := sorted({key for key in keys if key and keys.count(key) > 1}):
        problems.append(f"these columns have the same name once tidied: {', '.join(repeated)}")
    if reserved := sorted(set(keys) & RESERVED_KEYS):
        problems.append(
            f"rename {', '.join(reserved)}: the data model already loads it from another file"
        )
    if problems:
        raise SupplementalError("Fix the columns, then upload again: " + "; ".join(problems) + ".")

    id_at = lowered.index(ID_COLUMN.lower())
    year_at = lowered.index(YEAR_COLUMN.lower()) if has_year else None
    term_at = lowered.index(TERM_COLUMN.lower()) if has_term else None
    return id_at, year_at, term_at, values
