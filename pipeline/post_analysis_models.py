"""Validated model output and program-owned metadata for one archive record."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from scripts.x_archive_models import ArchiveModel

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
SummaryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Ticker = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{1,12}(?:[.:-][A-Z0-9]{1,8})?$")]


class EvidencePoint(ArchiveModel):
    text: Text
    evidence_ids: list[str] = Field(min_length=1, max_length=5)


class Summary(EvidencePoint):
    text: SummaryText


class Claim(EvidencePoint):
    category: Literal["fact", "opinion"]
    attribution: Text


class PostAnalysisDraft(ArchiveModel):
    research_value: Literal["actionable", "background"]
    summary: Summary | None
    author_opinion: EvidencePoint | None
    why_it_matters: EvidencePoint | None
    investment_implication: EvidencePoint | None
    counterevidence: list[EvidencePoint] = Field(max_length=3)
    risk_hypotheses: list[EvidencePoint] = Field(max_length=3)
    next_research_actions: list[EvidencePoint] = Field(max_length=3)
    related_sectors: list[Text] = Field(max_length=5)
    related_companies: list[Text] = Field(max_length=8)
    related_tickers: list[Ticker] = Field(max_length=8)
    claim_annotations: list[Claim] = Field(max_length=8)

    @model_validator(mode="after")
    def check_research_value(self):
        if self.research_value == "background" and (
            self.investment_implication or self.next_research_actions
        ):
            raise ValueError("背景材料不能附带投资假设或验证任务。")
        if self.research_value == "actionable" and not (
            self.summary and self.why_it_matters and self.investment_implication and self.next_research_actions
        ):
            raise ValueError("可研究线索需要核心观点、传导逻辑、研究假设和验证问题。")
        return self

    def cited_points(self):
        points = (self.summary, self.author_opinion, self.why_it_matters, self.investment_implication)
        return [point for point in points if point] + [
            *self.counterevidence, *self.risk_hypotheses,
            *self.next_research_actions, *self.claim_annotations,
        ]


class EvidenceSource(ArchiveModel):
    record_id: str
    kind: Literal["body", "quote", "image"]
    excerpt: str
    source_url: str | None
    source_verification: Literal["pending", "missing", "verified"]
    content_verification: Literal["pending", "verified"]
    attribution: str | None
    media_id: str | None = None


class PostAnalysisExample(ArchiveModel):
    analysis: PostAnalysisDraft
    evidence: dict[str, EvidenceSource]
    media_analysis_status: Literal["no_media", "not_analyzed"]


class PostAnalysis(ArchiveModel):
    schema_version: Literal[1] = 1
    analysis_status: Literal["completed"] = "completed"
    record_id: str
    source_record_ids: list[str]
    analysis: PostAnalysisDraft
    evidence: dict[str, EvidenceSource]
    fact_verification: Literal["unverified"] = "unverified"
    media_analysis_status: Literal["no_media", "not_analyzed", "partial", "analyzed"]
    prompt_version: str
    prompt_sha256: Digest
    input_sha256: Digest
    cache_key: Digest
    provider: str
    requested_model: str
    model_name: str = Field(min_length=1)
    request_id: str | None
    generated_at: AwareDatetime
