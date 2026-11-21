from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArchiveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class XLink(ArchiveModel):
    kind: Literal["missing", "invalid", "profile", "other_x_path", "status"]
    url: str | None = None
    post_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    author_handle: str | None = None


class Media(ArchiveModel):
    media_id: str
    media_type: Literal["image"] = "image"
    original_filename: str
    excel_row: int = Field(ge=2)
    position: int = Field(ge=1)
    local_path: str | None = None
    public_path: Literal[None] = None
    exists: bool
    availability: Literal[
        "available", "filename_match", "missing", "outside_archive",
        "conflict", "unreadable", "invalid_file", "unsupported_extension",
    ]
    analysis_status: Literal["not_analyzed"] = "not_analyzed"
    description: Literal[None] = None

    @field_validator("local_path")
    @classmethod
    def relative_media_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        path = PurePosixPath(value)
        if path.is_absolute() or path.parts[:1] != ("media",) or len(path.parts) < 2:
            raise ValueError("图片路径必须相对于原始数据目录，并位于 media 下")
        if ".." in path.parts or ":" in value or "\\" in value:
            raise ValueError("图片路径含不允许的片段")
        return value


class Post(ArchiveModel):
    record_id: str
    excel_row: int = Field(ge=2)
    post_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    monitored_account: str | None
    author_display_name: str | None
    source_author_handle: str | None
    posted_date: date | None
    posted_date_raw: str | None
    posted_at: datetime | None = None
    collected_at: datetime | None = None
    content: str = Field(min_length=1)
    text_origin_status: Literal[
        "unknown_manual_entry", "original", "translation", "manual_summary",
    ] = "unknown_manual_entry"
    source_url: str | None
    source_url_status: Literal["missing", "invalid", "profile", "other_x_path", "status"]
    source_verification: Literal["pending", "missing", "verified"]
    content_verification: Literal["pending", "verified"] = "pending"
    quoted_content: str | None
    quoted_url: str | None
    quoted_url_status: Literal["missing", "invalid", "profile", "other_x_path", "status"]
    quoted_post_id: str | None = Field(default=None, pattern=r"^[0-9]+$")
    quoted_author_handle: str | None
    quoted_text_origin_status: Literal["unknown_manual_entry"] | None
    quoted_source_verification: Literal["pending", "missing"]
    media: list[Media]
    data_origin: Literal["manual_archive"] = "manual_archive"
    is_demo: Literal[False] = False
    analysis_status: Literal["not_analyzed"] = "not_analyzed"
    analysis_at: datetime | None = None


class Relation(ArchiveModel):
    kind: Literal["shared_post_id", "identical_content", "numbered_thread_candidate", "archive_quote"]
    record_ids: list[str] = Field(min_length=2)
    excel_rows: list[int] = Field(min_length=2)


class Issue(ArchiveModel):
    code: str
    excel_rows: list[int] = Field(min_length=1)
    detail: str
    recommendation: str


class ImportResult(ArchiveModel):
    schema_version: Literal[1] = 1
    source_file: str
    sheet: str
    workbook_sha256: str
    data_rows: int = Field(ge=0)
    embedded_media_files: int = Field(ge=0)
    posts: list[Post]
    relations: list[Relation]
    issues: list[Issue]

