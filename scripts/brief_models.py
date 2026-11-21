"""Version-one contracts for offline brief preparation and replay."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from .x_archive_models import ArchiveModel, Post

Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
NonEmpty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
ExactQuote = Annotated[str, StringConstraints(min_length=1, max_length=1000)]
StableKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")]
Coordinate = Annotated[float, Field(ge=0, le=1, strict=True)]
ImageRegion = tuple[Coordinate, Coordinate, Coordinate, Coordinate]
BRIEF_ARCHIVE_BUCKETS = {"rehearsal": "rehearsals", "replay": "replays", "api": "generated"}


class InputImage(ArchiveModel):
    media_id: str
    local_path: str
    sha256: Digest


class InputPacket(ArchiveModel):
    schema_version: Literal[1] = 1
    date: date
    archive_sha256: Digest
    workbook_sha256: Digest
    records: list[Post] = Field(min_length=1)
    images: list[InputImage]

    @model_validator(mode="after")
    def validate_scope(self):
        ids = {post.record_id for post in self.records}
        if len(ids) != len(self.records) or any(post.posted_date != self.date for post in self.records):
            raise ValueError("输入记录必须属于同一天且记录标识唯一。")
        known = {asset.media_id for post in self.records for asset in post.media}
        supplied = {image.media_id for image in self.images}
        if len(supplied) != len(self.images) or not supplied <= known:
            raise ValueError("输入图片必须属于当日记录且标识唯一。")
        return self


class TextReference(ArchiveModel):
    kind: Literal["body", "quote"]
    record_id: str
    excerpt: ExactQuote


class ImageReference(ArchiveModel):
    kind: Literal["image"]
    record_id: str
    media_id: str
    region: ImageRegion

    @model_validator(mode="after")
    def valid_region(self):
        left, top, right, bottom = self.region
        if left >= right or top >= bottom:
            raise ValueError("图片区域的右、下边界必须大于左、上边界。")
        return self


Reference = Annotated[TextReference | ImageReference, Field(discriminator="kind")]


class ExtractItem(ArchiveModel):
    item_id: StableKey
    category: Literal["fact", "opinion", "inference"]
    text: NonEmpty
    evidence: list[Reference] = Field(min_length=1)


class ChartValue(ArchiveModel):
    label: NonEmpty
    printed_value: NonEmpty
    unit: NonEmpty | None = None


class ImageReading(ArchiveModel):
    media_id: str
    status: Literal["readable", "unreadable", "not_read"]
    chart_title: NonEmpty | None = None
    unit: NonEmpty | None = None
    printed_source: NonEmpty | None = None
    x_axis: NonEmpty | None = None
    y_axis: NonEmpty | None = None
    observation: NonEmpty | None = None
    values: list[ChartValue] = Field(default_factory=list)

    @model_validator(mode="after")
    def readable_fields(self):
        fields = (self.chart_title, self.unit, self.printed_source, self.x_axis, self.y_axis, self.observation, self.values)
        if self.status != "readable" and any(fields):
            raise ValueError("未读取或无法可靠识别的图片必须将图表字段置空。")
        if self.status == "readable" and not self.observation:
            raise ValueError("可读图片需说明观察到的内容。")
        return self


class PostExtraction(ArchiveModel):
    record_id: str
    items: list[ExtractItem]
    images: list[ImageReading]


class Extraction(ArchiveModel):
    schema_version: Literal[1] = 1
    input_sha256: Digest
    posts: list[PostExtraction]


class CitedPoint(ArchiveModel):
    text: NonEmpty
    item_ids: list[StableKey] = Field(min_length=1)


class Hypothesis(ArchiveModel):
    comparison_key: StableKey
    statement: NonEmpty
    support_item_ids: list[StableKey] = Field(min_length=1)
    counter_item_ids: list[StableKey]
    questions: list[NonEmpty] = Field(min_length=1)


class DailyBrief(ArchiveModel):
    schema_version: Literal[1] = 1
    date: date
    input_sha256: Digest
    extraction_sha256: Digest
    summary: CitedPoint | None
    events: list[CitedPoint]
    themes: list[CitedPoint]
    hypotheses: list[Hypothesis]
    questions: list[CitedPoint]
    risks: list[CitedPoint]


class PromptVersion(ArchiveModel):
    name: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*\.v[0-9]+\.md$")]
    sha256: Digest
    schema_sha256: Digest


class RunMetadata(ArchiveModel):
    run_id: Digest
    generated_at: datetime
    mode: Literal["rehearsal", "replay", "api"]
    provider: str
    model: str | None
    input_sha256: Digest
    extraction_sha256: Digest
    brief_sha256: Digest
    extract_prompt: PromptVersion
    report_prompt: PromptVersion

