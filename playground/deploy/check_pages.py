"""Fail if the trimmed measures file changes any answer the pages on the query builder can give.

Run from playground/server_application:
    PYTHONPATH=. uv run python ../deploy/check_pages.py <full file> <trimmed file>

It asks the de-aggregation, course outcomes and aid momentum pages every choice their pickers offer,
the executive view its published headline tiles and gaps card for every cohort lens, and the chat
every published trend (each single-cohort measure's everyone row, with include trends), once per
file, and compares the answers. The executive view's graduation tile and filtered tiles are counted
live from the data model, so they aren't asked.
"""

import json
import os
import sys
from itertools import product
from typing import get_args

from app.sandbox.aid_momentum import results as aid_momentum
from app.sandbox.aid_momentum.schemas import Measure
from app.sandbox.course_outcomes.results import get_courses, get_midterm_alerts
from app.sandbox.course_outcomes.schemas import GenderChoice, RaceChoice, Sort
from app.sandbox.deaggregation.results import get_outcomes
from app.sandbox.deaggregation.schemas import Gender, Race
from app.sandbox.executive_view import published as executive_published
from app.sandbox.executive_view import results as executive
from app.sandbox.executive_view.schemas import CohortLens
from app.sandbox.results import published
from app.sandbox.results.schemas import QuerySpec

# The course outcomes slider runs from 10 to 2000 graded enrollments.
MIN_ENROLLMENTS = [10, 50, 100, 200, 500, 2000]
AID_MOMENTUM = [aid_momentum.get_bands, aid_momentum.get_gaps, aid_momentum.get_pell]


def executive_kpis(lens: CohortLens) -> str:
    """The executive view's published headline rows and specs for one lens, as JSON."""
    tiles = executive_published.published_kpis(lens)
    rows = {measure: row.model_dump() for measure, row in tiles.rows.items()}
    return json.dumps({"rows": rows, "specs": [spec.model_dump() for spec in tiles.specs]})


def published_trends() -> list[str]:
    """Every single-cohort measure's everyone row and trends, as the chat reads them, as JSON."""
    found = []
    for measure, approved in sorted(published.reader().approved().items()):
        for cohort in approved["cohorts"]:
            if "+" in cohort:
                continue  # a pool has no trend
            breakdowns = published.reader().breakdowns(measure, cohort)
            spec = QuerySpec(
                measure=measure, cohort=cohort, group_by=breakdowns[0], include=["rates", "trends"]
            )
            found.append(published.page_answer(spec).model_dump_json())
    return found


def answers(path: str) -> list[str]:
    """Every answer the pages on the query builder can give, read from one measures file."""
    os.environ["RESULTS_DB"] = path
    published.reader.cache_clear()  # the builder is cached, so point it at this file
    groups = list(product(get_args(Race), get_args(Gender)))
    # Course outcomes' pickers also offer "all" for race and for gender.
    course_groups = list(product(get_args(RaceChoice), get_args(GenderChoice)))
    outcomes = [get_outcomes(*group) for group in groups]
    courses = [
        get_courses(*group, minimum, sort)
        for group in course_groups
        for minimum in MIN_ENROLLMENTS
        for sort in get_args(Sort)
    ]
    midterms = [
        get_midterm_alerts(*group, minimum)
        for group in course_groups
        for minimum in MIN_ENROLLMENTS
    ]
    aid = [read(measure) for measure in get_args(Measure) for read in AID_MOMENTUM]
    gaps = [executive.get_gaps(lens) for lens in get_args(CohortLens)]
    pages = [answer.model_dump_json() for answer in [*outcomes, *courses, *midterms, *aid, *gaps]]
    kpis = [executive_kpis(lens) for lens in get_args(CohortLens)]
    return [*pages, *kpis, *published_trends()]


def main() -> None:
    """Compare both files' answers, and exit 1 if any differs."""
    full, trimmed = answers(sys.argv[1]), answers(sys.argv[2])
    if full != trimmed:
        sys.exit("The trimmed measures file changes a page on the query builder. Don't deploy it.")
    print(f"Same answers from both files, for all {len(full)} choices on the pages and the chat.")


if __name__ == "__main__":
    main()
