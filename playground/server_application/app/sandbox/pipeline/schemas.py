"""Request and response shapes for the Sandbox pipeline: uploads, load runs and table previews."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SourceKind = Literal["cohort", "course"]
# An upload is a cohort or course file, or an institution's supplemental file.
UploadKind = Literal["cohort", "course", "supplemental"]
RunState = Literal["running", "succeeded", "failed"]

DATA_NOTE = (
    "Loaded with the normalized data model's own pipeline. The shared mock data is synthetic: "
    "nothing built on it is a finding about real students or institutions."
)


class SupplementalSummary(BaseModel):
    """What a supplemental upload holds once its columns become attributes."""

    rows_read: int
    facts: int = Field(description="Values it will load: one per student (and term) and column.")
    rows_set_aside: int = Field(
        description="Rows with no usable student ID, or a bad year or term."
    )
    attributes: list[str] = Field(description="The attribute name each value column becomes.")
    per_term: bool = Field(description="True when each value belongs to a term.")
    source: str | None = Field(
        default=None, description="The source its values record in student_attribute."
    )


class Upload(BaseModel):
    """One stored file, ready to be loaded as the cohort or course file, or as supplemental data."""

    upload_id: str
    kind: UploadKind
    filename: str = Field(description="The name the file was uploaded with.")
    size_bytes: int
    sha256: str
    uploaded_at: datetime
    unexpected_columns: list[str] = Field(
        default=[], description="Columns the mapping config doesn't read. The loader ignores them."
    )
    supplemental: SupplementalSummary | None = None
    values_loaded: int | None = Field(
        default=None,
        description="A supplemental upload's values in the database now; null for other kinds.",
    )


class RemovedUpload(BaseModel):
    """An upload that was removed, with how many of its values left the database."""

    upload_id: str
    filename: str
    values_removed: int


class BuiltInFile(BaseModel):
    """A supplemental file that's part of the data model itself: read-only, never removed here."""

    file: str
    values: int = Field(description="Its values in the database now.")
    attributes: list[str] = Field(description="The attribute names its columns load as.")


class UploadList(BaseModel):
    """Every stored upload, newest first, and the data model's built-in supplemental files."""

    uploads: list[Upload]
    built_in: list[BuiltInFile] = []


class RunRequest(BaseModel):
    """Which uploads to load. A file left out is the repo's configured mock file."""

    cohort_upload_id: str | None = None
    course_upload_id: str | None = None
    supplemental_upload_ids: list[str] = Field(
        default=[], description="Supplemental uploads to load with them, into student_attribute."
    )


class SupplementalResult(BaseModel):
    """How one supplemental upload loaded."""

    upload_id: str
    filename: str
    facts_loaded: int
    facts_held_back: int = Field(
        description="Values whose student isn't in the loaded cohort file."
    )


class PublishResult(BaseModel):
    """Whether a run rebuilt the published results that the results pages read.

    It doesn't change the run's own status: the tables stay loaded whatever happens here.
    """

    status: Literal["running", "published", "skipped", "failed"]
    message: str
    manifest_version: int | None = None
    data_loaded_at: str | None = Field(
        default=None, description="When the data the new results came from was loaded."
    )


class RunStatus(BaseModel):
    """One load run: running, or how it ended."""

    run_id: str
    status: RunState
    cohort_upload_id: str | None = None
    course_upload_id: str | None = None
    supplemental_upload_ids: list[str] = []
    supplemental: list[SupplementalResult] = []
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: list[str] = Field(default=[], description="One line per finished pipeline step.")
    error_kind: Literal["invalid_input", "load_failed"] | None = None
    error: str | None = None
    summary: dict[str, Any] | None = Field(
        default=None,
        description="The loader's summary.yaml, with held_back replaced by a held_back_rows count.",
    )
    publish: PublishResult | None = Field(
        default=None,
        description="The published results rebuild after the load; null until the load succeeds.",
    )
    note: str = DATA_NOTE


class TableSummary(BaseModel):
    """One model table and how many rows it holds; row_count is null before the first load."""

    name: str
    row_count: int | None


class TableList(BaseModel):
    """Every model table, in the order the loader fills them."""

    tables: list[TableSummary]
    note: str = DATA_NOTE


class TableRows(BaseModel):
    """One page of a model table's rows."""

    name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    limit: int
    offset: int = 0
    note: str = DATA_NOTE
