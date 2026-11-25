"""Run the data model's loader into the Playground's database, and read its tables back.

The loader is synchronous and takes a while, so a run goes to a worker thread and the request
returns at once; the UI polls the run's status. One run at a time: a load replaces every model
table, so two at once would race. Run status lives in this process, so it's lost on restart and
assumes one server worker; the loader's own summary.yaml is the lasting record, and is read back
for a run this process doesn't know.

Once the tables load, the run also rebuilds the published results file (measures/publish.py) that
De-aggregation, Course outcomes, Aid momentum and the Executive view's tiles read, so one upload
updates every view. That takes about a minute more and is reported as the run's publish. It never
undoes the load: a publish that fails or can't write its file leaves the tables loaded and the
earlier results in place, and says why.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from functools import cache
from typing import Any

import pdp_model
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.sandbox.chat import query_tool
from app.sandbox.chat.repo import RepoNotFound, import_path
from app.sandbox.results import published

from . import uploads
from .schemas import (
    BuiltInFile,
    PublishResult,
    RemovedUpload,
    RunRequest,
    RunStatus,
    SourceKind,
    SupplementalResult,
    TableRows,
    TableSummary,
    Upload,
)
from .supplemental import MAPPING, TERM_MAPPING

logger = logging.getLogger(__name__)

# Playground loads write their table files here, not to output/tables/, which other tools read.
TABLES_DIR = pdp_model.MODEL_DIR / "output/playground/tables"

PUBLISH_RUNNING = "Rebuilding the published results (about a minute)."
PUBLISHED = "Published results rebuilt from this load."
PUBLISH_READ_ONLY = (
    "This server can't write the published results file (a deployed or read-only disk), so "
    "De-aggregation, Course outcomes, Aid momentum and the Executive view's tiles still show the "
    "results it was built with."
)
PUBLISH_UNAVAILABLE = (
    "The measures code isn't available here, so the published results weren't rebuilt: {error}."
)
UNEXPECTED_ERROR = "an unexpected error; see the API log"
PUBLISH_FAILED = (
    "Tables loaded, but the published results weren't rebuilt: {error}. Those views still show "
    "the earlier results."
)

_runs: dict[str, RunStatus] = {}
_active_run: str | None = None
_tasks: set[asyncio.Task[None]] = set()  # keeps each running task referenced until it ends


class RunRefused(Exception):
    """A run wasn't started; status_code is the HTTP status to answer with."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@cache
def model_tables() -> tuple[str, ...]:
    """The data model's tables, in the order the loader fills them."""
    return tuple(pdp_model.table_names())


def start_run(request: RunRequest) -> RunStatus:
    """Start loading the chosen uploads in the background. Returns the run's first status."""
    global _active_run
    cohort = _upload_file(request.cohort_upload_id, "cohort")
    course = _upload_file(request.course_upload_id, "course")
    extra = [_supplemental_upload(upload_id) for upload_id in request.supplemental_upload_ids]
    if _active_run is not None:
        raise RunRefused(409, f"Run {_active_run} is still loading. Wait for it to finish.")
    status = RunStatus(
        run_id=pdp_model.new_run_id(),
        status="running",
        cohort_upload_id=request.cohort_upload_id,
        course_upload_id=request.course_upload_id,
        supplemental_upload_ids=request.supplemental_upload_ids,
        started_at=datetime.now(UTC),
    )
    _runs[status.run_id] = status
    _active_run = status.run_id  # set before any await, so a second request sees it
    task = asyncio.create_task(_load(status, cohort, course, extra))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return status


async def list_uploads(session: AsyncSession) -> list[Upload]:
    """Every stored upload, newest first, with a supplemental upload's values in the database."""
    found = uploads.list_uploads()
    if "student_attribute" not in await _existing_tables(session):
        return found
    counted = []
    for upload in found:
        source = uploads.source_of(upload)
        # Values shared with another upload can't be counted as this one's.
        if source is not None and not uploads.source_is_shared(upload, found):
            result = await session.execute(
                text("SELECT COUNT(*) FROM student_attribute WHERE source = :source"),
                {"source": source},
            )
            upload = upload.model_copy(update={"values_loaded": int(result.scalar_one())})
        counted.append(upload)
    return counted


async def built_in_files(session: AsyncSession) -> list[BuiltInFile]:
    """The data model's built-in supplemental files in the database, read-only.

    Their sources start with "supplemental:", as all_students_extras.csv's does. They aren't
    uploads, so they can't be removed here.
    """
    if "student_attribute" not in await _existing_tables(session):
        return []
    result = await session.execute(
        text(
            "SELECT source, attribute_key, COUNT(*) FROM student_attribute "
            "WHERE source LIKE 'supplemental:%' GROUP BY source, attribute_key "
            "ORDER BY source, MIN(attribute_id)"
        )
    )
    files: dict[str, BuiltInFile] = {}
    for source, key, count in result.all():
        name = str(source).removeprefix("supplemental: ").split(" (")[0]
        found = files.setdefault(str(source), BuiltInFile(file=name, values=0, attributes=[]))
        found.values += int(count)
        found.attributes.append(str(key))
    return list(files.values())


async def remove_upload(session: AsyncSession, upload_id: str) -> RemovedUpload:
    """Delete an upload: a supplemental upload's values in the database first, then its files.

    Refused while a load runs, since the load could be reading the file or writing the table.
    """
    upload = uploads.get_upload(upload_id)
    if upload is None:
        raise RunRefused(404, f"No upload {upload_id!r}.")
    if _active_run is not None:
        raise RunRefused(409, f"Run {_active_run} is loading. Wait for it to finish.")
    removed = 0
    source = uploads.source_of(upload)
    # An older upload whose source another upload shares: its values can't be told apart from
    # the other's, so only its files go.
    shared = uploads.source_is_shared(upload, uploads.list_uploads())
    if source is not None and not shared and "student_attribute" in await _existing_tables(session):
        result = await session.execute(
            text("DELETE FROM student_attribute WHERE source = :source"), {"source": source}
        )
        await session.commit()
        removed = result.rowcount or 0
    uploads.delete_upload(upload)
    return RemovedUpload(upload_id=upload_id, filename=upload.filename, values_removed=removed)


def get_run(run_id: str) -> RunStatus | None:
    """A run's status: from this process if it started it, else from the loader's summary.yaml."""
    if run_id in _runs:
        return _runs[run_id]
    report = pdp_model.load_report(run_id) if run_id.replace("-", "").isalnum() else None
    if report is None:
        return None
    return RunStatus(
        run_id=run_id,
        status="succeeded" if report.get("status") == "loaded" else "failed",
        started_at=report.get("started_at"),
        finished_at=report.get("finished_at"),
        error=report.get("error"),
        summary=_short_summary(report),
    )


async def table_summaries(session: AsyncSession) -> list[TableSummary]:
    """Every model table with its row count; null for a table that isn't in the database yet."""
    existing = await _existing_tables(session)
    summaries = []
    for name in model_tables():
        count = None
        if name in existing:
            count = (await session.execute(text(f'SELECT COUNT(*) FROM "{name}"'))).scalar_one()
        summaries.append(TableSummary(name=name, row_count=count))
    return summaries


async def table_rows(
    session: AsyncSession, name: str, limit: int, offset: int = 0
) -> TableRows | None:
    """One page of a model table (name) in primary key order, or None if it hasn't been loaded."""
    if name not in await _existing_tables(session):
        return None
    connection = await session.connection()
    key = await connection.run_sync(
        lambda sync: inspect(sync).get_pk_constraint(name)["constrained_columns"]
    )
    # A fixed order keeps pages from repeating or skipping rows; "1" is the first column.
    order = ", ".join(f'"{column}"' for column in key) or "1"
    # Safe to put in the SQL: name comes from model_tables() and key from that table's schema.
    result = await session.execute(
        text(f'SELECT * FROM "{name}" ORDER BY {order} LIMIT :limit OFFSET :offset'),
        {"limit": limit, "offset": offset},
    )
    columns = list(result.keys())
    rows = [dict(row) for row in result.mappings()]
    return TableRows(name=name, columns=columns, rows=rows, limit=limit, offset=offset)


async def _load(
    status: RunStatus, cohort: str | None, course: str | None, extra: list[Upload]
) -> None:
    """Run the loader in a worker thread and record how it ended."""
    global _active_run
    try:
        summary = await asyncio.to_thread(
            pdp_model.run_load,
            settings.DATABASE_URL,
            status.run_id,
            cohort=cohort,
            course=course,
            progress=status.progress.append,
            tables_dir=TABLES_DIR,
            supplemental=[_loader_source(upload) for upload in extra],
        )
        status.summary = _short_summary(summary)
        status.supplemental = [_supplemental_result(upload, summary) for upload in extra]
    except pdp_model.ConfigError as error:
        _fail(status, "invalid_input", error)
    except Exception as error:  # the loader rolls back and raises RuntimeError; others are bugs
        if not isinstance(error, RuntimeError):
            logger.exception("Load run %s failed unexpectedly", status.run_id)
        _fail(status, "load_failed", error)
    else:
        # The tables are in, so the results pages can be rebuilt from them. This is outside the
        # load's try, so nothing here can mark the load failed: publish reports for itself.
        status.publish = PublishResult(status="running", message=PUBLISH_RUNNING)
        try:
            status.publish = await asyncio.to_thread(_publish)
        except Exception:  # _publish catches its own errors, so this is a bug in it
            logger.exception("Publishing after load run %s failed unexpectedly", status.run_id)
            status.publish = _publish_failed(UNEXPECTED_ERROR)
        status.progress.append(f"publish: {status.publish.message}")
        status.status = "succeeded"
    finally:
        status.finished_at = datetime.now(UTC)
        _active_run = None


def _publish() -> PublishResult:
    """Rebuild the published results from the tables just loaded, into the file reader() reads."""
    try:
        results, manifest = published.publish_target()
        import_path(".")
        from measures.publish import publish  # type: ignore[import-not-found]
    except (RepoNotFound, ImportError) as error:
        return PublishResult(status="skipped", message=PUBLISH_UNAVAILABLE.format(error=error))
    try:
        results.parent.mkdir(parents=True, exist_ok=True)
        writable = os.access(results.parent, os.W_OK)
    except OSError:
        writable = False
    if not writable:
        return PublishResult(status="skipped", message=PUBLISH_READ_ONLY)
    try:
        # The measures only read, so the read-only connection the chat's queries use is enough.
        with query_tool.backend().connect() as connection:
            record = publish(connection, results=results, manifest_path=manifest)
    except ValueError as error:
        # publish's own refusal, such as a cohort year the upload doesn't have: safe to show.
        return _publish_failed(str(error))
    except Exception:
        # Anything else can carry paths or connection details, so the browser gets a generic reason.
        logger.exception("Publishing the results after a load failed unexpectedly")
        return _publish_failed(UNEXPECTED_ERROR)
    return PublishResult(
        status="published",
        message=PUBLISHED,
        manifest_version=record["manifest_version"],
        data_loaded_at=str(record["data_loaded_at"]),
    )


def _publish_failed(reason: str) -> PublishResult:
    """A failed publish, saying the tables loaded and the published views kept their results."""
    return PublishResult(status="failed", message=PUBLISH_FAILED.format(error=reason))


def _fail(status: RunStatus, kind: str, error: Exception) -> None:
    """Record a failed run, with the loader's summary when it wrote one."""
    status.status = "failed"
    status.error_kind = kind
    status.error = str(error)
    report = pdp_model.load_report(status.run_id)
    status.summary = _short_summary(report) if report else None


def _upload_file(upload_id: str | None, kind: SourceKind) -> str | None:
    """The stored file for an upload id, checked to be the right kind; None for no upload."""
    if upload_id is None:
        return None
    upload = uploads.get_upload(upload_id)
    if upload is None:
        raise RunRefused(404, f"No upload {upload_id!r}.")
    if upload.kind != kind:
        raise RunRefused(422, f"Upload {upload_id} is a {upload.kind} file, not a {kind} file.")
    return str(uploads.upload_path(upload))


def _supplemental_upload(upload_id: str) -> Upload:
    """A stored supplemental upload, or RunRefused."""
    upload = uploads.get_upload(upload_id)
    if upload is None:
        raise RunRefused(404, f"No upload {upload_id!r}.")
    if upload.kind != "supplemental" or upload.supplemental is None:
        raise RunRefused(
            422, f"Upload {upload_id} is a {upload.kind} file, not a supplemental file."
        )
    return upload


def _loader_source(upload: Upload) -> tuple[str, str, str]:
    """(path, mapping config, provider) for the loader's supplemental argument."""
    per_term = upload.supplemental is not None and upload.supplemental.per_term
    mapping = TERM_MAPPING if per_term else MAPPING
    return str(uploads.supplemental_path(upload)), mapping, f"uploaded: {upload.filename}"


def _supplemental_result(upload: Upload, summary: dict[str, Any]) -> SupplementalResult:
    """How many of an upload's values loaded, and how many the loader held back."""
    name = uploads.supplemental_path(upload).name
    held_back = sum(
        str(row.get("source_file", "")).endswith(name) for row in summary.get("held_back") or []
    )
    facts = upload.supplemental.facts if upload.supplemental else 0
    return SupplementalResult(
        upload_id=upload.upload_id,
        filename=upload.filename,
        facts_loaded=facts - held_back,
        facts_held_back=held_back,
    )


def _short_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """The summary without its per-row held_back list, which can run to thousands of entries.

    held_back_rows counts only the cohort and course files' rows. The repo's enrichment files
    cover the full mock data, so their rows for students outside an upload are expected.
    """
    short = {key: value for key, value in summary.items() if key != "held_back"}
    # The cohort and course files share the load's validation run; each enrichment file has its own.
    core_files = {
        name
        for name, counts in (summary.get("validation") or {}).items()
        if counts.get("run_id") == summary.get("run_id")
    }
    held_back = summary.get("held_back") or []
    short["held_back_rows"] = sum(row.get("source_file") in core_files for row in held_back)
    return short


async def _existing_tables(session: AsyncSession) -> set[str]:
    """The model tables that are in the database now."""
    connection = await session.connection()
    names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    return set(names) & set(model_tables())
