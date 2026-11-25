"""Which published results file the Sandbox reads, and the one query builder over it.

The results route, the chatbot and the pages built on the builder all call reader() through this
module, so a test that monkeypatches published.reader points every caller at its own file.
"""

import os
import sqlite3
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from app.core.config import settings
from app.sandbox.chat.repo import RepoNotFound, import_path

from .schemas import QueryAnswer, QuerySpec


class ResultsUnavailable(RuntimeError):
    """A page can't read its numbers from the published results: a server problem, so a 503."""


class NoMatchingGroups(ResultsUnavailable):
    """No published group, shown or hidden, matches the spec's where.

    The deploy's trimmed copy drops hidden course groups, so a group hidden in every course has no
    course rows there at all. A page that pairs rows by course reads that as every course hidden.
    """


def results_path() -> Path | None:
    """RESULTS_DB, else DEAGGREGATION_DB, else None for the builder's own default.

    Each is read from the real environment first, then from the .env files through settings.
    The deploy already sets DEAGGREGATION_DB to its copy of the same measures file.
    """
    path = (
        os.environ.get("RESULTS_DB")
        or os.environ.get("DEAGGREGATION_DB")
        or settings.RESULTS_DB
        or settings.DEAGGREGATION_DB
    )
    return Path(path) if path else None


@cache
def reader() -> Any:
    """The query builder over the published results."""
    import_path("mcp")
    from pdp_mcp.results import ResultsReader  # type: ignore[import-not-found]

    path = results_path()
    return ResultsReader(results_path=path) if path else ResultsReader()


def publish_target() -> tuple[Path, Path]:
    """(results file, manifest) that reader() reads, so a publish writes exactly what it reads."""
    results = reader()
    return Path(results.results_path), Path(results.manifest_path)


def page_answer(spec: QuerySpec) -> QueryAnswer:
    """Every row a page's fixed spec asks for, uncapped, or ResultsUnavailable saying why not.

    The spec is the page's own, not a caller's, so a refusal is never the caller's to fix.
    """
    try:
        results = reader()
        from pdp_mcp.results import Spec, SpecRefused  # type: ignore[import-not-found]
    except (RepoNotFound, ImportError) as error:
        raise ResultsUnavailable(f"The query builder isn't available here: {error}") from error
    try:
        answer = results.query(Spec(**spec.model_dump()), max_rows=None)
    except SpecRefused as error:
        # The builder names the published values only when where matched no group at all.
        if "values" in error.approved:
            raise NoMatchingGroups(str(error)) from error
        raise ResultsUnavailable(str(error)) from error
    except (FileNotFoundError, sqlite3.Error, yaml.YAMLError) as error:
        raise ResultsUnavailable(f"The published results couldn't be read: {error}") from error
    return QueryAnswer.model_validate(answer.model_dump())
