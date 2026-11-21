"""Validated data contracts for research briefs and their editorial input."""
from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_serializer, model_validator

from .brief_models import Digest, NonEmpty, StableKey
from .x_archive_models import ArchiveModel


class Assessment(ArchiveModel):
    level: Literal[0, 1, 2]
    reason: NonEmpty


class Criteria(ArchiveModel):
    investment_importance: Assessment
    information_increment: Assessment
    research_value: Assessment
    verifiability: Assessment


class LeadInsight(ArchiveModel):
    title: NonEmpty
    explanation: NonEmpty
    related_sectors: list[NonEmpty]
    related_tickers: list[NonEmpty]
    item_ids: list[StableKey] = Field(min_length=1)


class CompanyScope(ArchiveModel):
    direct: list[NonEmpty]
    value_chain: list[NonEmpty]


class SignalCandidate(ArchiveModel):
    event_key: StableKey
    theme_key: StableKey
    title: NonEmpty
    what_happened: list[StableKey] = Field(min_length=1)
    why_it_matters: NonEmpty
    investment_implication: NonEmpty
    bull_case: list[StableKey]
    bear_case: list[StableKey]
    risks: NonEmpty
    next_research_action: NonEmpty
    related_tickers: list[NonEmpty]
    related_sectors: list[NonEmpty]
    selection_reason: NonEmpty
    criteria: Criteria
    core_judgment: NonEmpty | None = None
    company_scope: CompanyScope | None = None
    thesis_status: Literal["to_validate", "strengthened", "weakened", "invalidated"] | None = None

    @model_serializer(mode="wrap")
    def omit_missing_editorial_fields(self, handler):
        data = handler(self)
        # Preserve historical draft and report fingerprints.
        for field in ("core_judgment", "company_scope", "thesis_status"):
            if data.get(field) is None:
                data.pop(field, None)
        return data


class ResearchTheme(ArchiveModel):
    theme_key: StableKey
    title: NonEmpty
    current_observation: NonEmpty
    related_companies: list[NonEmpty]
    item_ids: list[StableKey] = Field(min_length=1)
    conflicting_item_ids: list[StableKey]


class OtherUpdate(ArchiveModel):
    title: NonEmpty
    record_id: str
    industry: NonEmpty
    item_id: StableKey


class BriefDraft(ArchiveModel):
    lead_signal_key: StableKey | None
    lead_insight: LeadInsight | None
    candidates: list[SignalCandidate]
    research_themes: list[ResearchTheme]
    other_updates: list[OtherUpdate]
    limitations: list[NonEmpty]


class RankedSignal(SignalCandidate):
    evidence_quality: Assessment
    score: int = Field(ge=0, le=10)
    priority: Literal["core", "secondary", "general", "insufficient"]
    source_post_ids: list[str]
    verification_status: Literal["records_verified", "partially_verified", "pending"]


class Coverage(ArchiveModel):
    record_count: int = Field(ge=0)
    distinct_post_count: int = Field(ge=0)
    source_link_count: int = Field(ge=0)
    verified_source_count: int = Field(ge=0)
    image_count: int = Field(ge=0)


class VerificationSummary(ArchiveModel):
    verified: int = Field(ge=0)
    pending: int = Field(ge=0)
    missing: int = Field(ge=0)


class DailyBriefV2(ArchiveModel):
    schema_version: Literal[2] = 2
    report_date: date
    generated_at: datetime
    generation_mode: Literal["api", "replay"]
    prompt_version: NonEmpty
    model_name: NonEmpty
    input_post_ids: list[str]
    data_coverage: Coverage
    lead_insight: LeadInsight | None
    top_signals: list[RankedSignal] = Field(max_length=3)
    research_themes: list[ResearchTheme]
    other_updates: list[OtherUpdate]
    limitations: list[NonEmpty]
    source_verification_summary: VerificationSummary
    ranked_signals: list[RankedSignal]
    input_sha256: Digest
    extraction_sha256: Digest

    @model_validator(mode="after")
    def core_signals_match(self):
        if self.top_signals != [signal for signal in self.ranked_signals if signal.priority == "core"]:
            raise ValueError("核心信号与排序结果不一致。")
        if bool(self.lead_insight) != bool(self.top_signals):
            raise ValueError("核心观察必须对应有证据的核心信号。")
        return self
