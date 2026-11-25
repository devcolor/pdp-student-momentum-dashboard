"""Store uploaded cohort and course files where the data model's loader can read them.

Each upload gets its own folder, UPLOADS_DIR/<upload id>/, holding uploaded_<kind>.csv and an
upload.json describing it. The fixed file names keep every source's file name different, which the
loader needs: it names its reports by file name. Only the header is checked here; the loader's
validator checks the values when the upload is loaded.
"""

import csv
import hashlib
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

import pdp_model

from . import supplemental
from .schemas import SupplementalSummary, Upload, UploadKind

UPLOADS_DIR: Path = pdp_model.UPLOADS_DIR
_CHUNK_BYTES = 1024 * 1024
# Also keeps an id from naming a path outside UPLOADS_DIR.
_UPLOAD_ID = re.compile(r"^[0-9a-f]{32}$")


class UploadError(Exception):
    """An upload was refused; status_code is the HTTP status to answer with."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def save_upload(kind: UploadKind, filename: str, source: BinaryIO, max_bytes: int) -> Upload:
    """Copy an uploaded CSV into its own folder and check it.

    A cohort or course file's header is checked against its mapping config. A supplemental file is
    checked and turned into the long shape the data model loads (supplemental.convert).
    """
    if not filename.lower().endswith(".csv"):
        raise UploadError(422, f"{filename!r} isn't a .csv file.")
    upload_id = uuid.uuid4().hex
    folder = UPLOADS_DIR / upload_id
    folder.mkdir(parents=True)
    try:
        size, sha256 = _copy(source, folder / f"uploaded_{kind}.csv", max_bytes)
        unexpected, summary = [], None
        uploaded_at = datetime.now(UTC)
        if kind == "supplemental":
            tag = supplemental.source_tag(filename, uploaded_at.strftime("%Y-%m-%d"), upload_id)
            summary = _convert(folder / f"uploaded_{kind}.csv", upload_id, tag)
        else:
            unexpected = _check_header(kind, folder / f"uploaded_{kind}.csv")
    except BaseException:
        shutil.rmtree(folder)  # a refused upload leaves nothing behind
        raise
    upload = Upload(
        upload_id=upload_id,
        kind=kind,
        filename=filename,
        size_bytes=size,
        sha256=sha256,
        uploaded_at=uploaded_at,
        unexpected_columns=unexpected,
        supplemental=summary,
    )
    (folder / "upload.json").write_text(upload.model_dump_json(indent=2))
    return upload


def list_uploads() -> list[Upload]:
    """Every stored upload, newest first."""
    if not UPLOADS_DIR.is_dir():
        return []
    found = [
        Upload.model_validate_json(path.read_text()) for path in UPLOADS_DIR.glob("*/upload.json")
    ]
    return sorted(found, key=lambda upload: upload.uploaded_at, reverse=True)


def get_upload(upload_id: str) -> Upload | None:
    """The stored upload with this id, or None."""
    if not _UPLOAD_ID.match(upload_id):
        return None
    path = UPLOADS_DIR / upload_id / "upload.json"
    return Upload.model_validate_json(path.read_text()) if path.is_file() else None


def upload_path(upload: Upload) -> Path:
    """Where an upload's CSV is stored."""
    return UPLOADS_DIR / upload.upload_id / f"uploaded_{upload.kind}.csv"


def source_of(upload: Upload) -> str | None:
    """The source a supplemental upload's values record, or None for a cohort or course file.

    An upload from before the tag carried its id recorded only the file name and date.
    """
    if upload.kind != "supplemental" or upload.supplemental is None:
        return None
    if upload.supplemental.source:
        return upload.supplemental.source
    return f"uploaded: {upload.filename}, {upload.uploaded_at.strftime('%Y-%m-%d')}"


def source_is_shared(upload: Upload, others: list[Upload]) -> bool:
    """True if another stored upload's values record the same source, so they can't be told apart.

    Only an older upload can share one: its source had only the file name and date.
    """
    source = source_of(upload)
    return source is not None and any(
        other.upload_id != upload.upload_id and source_of(other) == source for other in others
    )


def delete_upload(upload: Upload) -> None:
    """Remove an upload's folder: its file, its long-shape file and upload.json."""
    shutil.rmtree(UPLOADS_DIR / upload.upload_id)


def supplemental_path(upload: Upload) -> Path:
    """Where a supplemental upload's long-shape file is stored."""
    return _long_path(upload.upload_id)


def _long_path(upload_id: str) -> Path:
    """The long-shape file's path. Its name is unique per upload: the loader names reports by it."""
    return UPLOADS_DIR / upload_id / f"supplemental_{upload_id[:12]}.csv"


def _convert(path: Path, upload_id: str, tag: str) -> SupplementalSummary:
    """Turn the institution's file into the long shape, beside it, or raise UploadError."""
    try:
        found = supplemental.convert(path, _long_path(upload_id), tag)
    except supplemental.SupplementalError as error:
        raise UploadError(422, str(error)) from error
    return SupplementalSummary(**vars(found), source=tag)


def _copy(source: BinaryIO, target: Path, max_bytes: int) -> tuple[int, str]:
    """Copy in chunks, stopping at max_bytes. Returns (size, SHA-256)."""
    size, digest = 0, hashlib.sha256()
    with open(target, "wb") as out:
        while chunk := source.read(_CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise UploadError(413, f"The file is larger than {max_bytes // (1024 * 1024)} MB.")
            digest.update(chunk)
            out.write(chunk)
    if size == 0:
        raise UploadError(422, "The file is empty.")
    return size, digest.hexdigest()


def _check_header(kind: UploadKind, path: Path) -> list[str]:
    """Refuse a file missing a column the mapping config reads. Returns the columns it doesn't read.

    Needed because the mapper reads a missing column as blank, so it would load without failing.
    """
    try:
        # Read as the mapper reads it, so a byte-order mark shows up here as it would there.
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), [])
    except UnicodeDecodeError as error:
        raise UploadError(422, f"The file isn't UTF-8 text: {error}") from error
    missing = [c for c in pdp_model.expected_columns(kind) if c not in header]
    if missing:
        hint = (
            " The first column starts with a byte-order mark: save it as CSV without one."
            if header and header[0].startswith("\ufeff")
            else ""
        )
        raise UploadError(
            422, f"The {kind} file is missing {len(missing)} columns: {', '.join(missing)}.{hint}"
        )
    known = set(pdp_model.expected_columns(kind, include_dropped=True))
    return [c for c in header if c not in known]
