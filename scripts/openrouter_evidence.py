"""Anchor text-model evidence to exact excerpts selected from the archive."""

import re
from typing import Literal

from pydantic import Field

from .brief_models import (
    Extraction, ExtractItem, ImageReading, InputPacket, NonEmpty, PostExtraction, StableKey, TextReference,
)
from .x_archive_models import ArchiveModel

MAX_EXCERPT_LENGTH = 1000
SENTENCE_BREAK = re.compile(r"(?<=[。！？；!?;])|(?<=\\.)\\s+|[\\r\\n]+")


class AnchoredItem(ArchiveModel):
    category: Literal["fact", "opinion", "inference"]
    text: NonEmpty
    segment_ids: list[StableKey] = Field(min_length=1)


class AnchoredExtraction(ArchiveModel):
    items: list[AnchoredItem]


def select_passages(packet: InputPacket) -> dict[str, TextReference]:
    passages = {}
    for post in packet.records:
        for kind, source in (("body", post.content), ("quote", post.quoted_content)):
            if not source:
                continue
            for sentence in SENTENCE_BREAK.split(source):
                for start in range(0, len(sentence), MAX_EXCERPT_LENGTH):
                    excerpt = sentence[start:start + MAX_EXCERPT_LENGTH].strip()
                    if excerpt:
                        segment_id = f"s-{len(passages) + 1}"
                        passages[segment_id] = TextReference(kind=kind, record_id=post.record_id, excerpt=excerpt)
    return passages


def attach_evidence(
    packet: InputPacket, output: AnchoredExtraction, passages: dict[str, TextReference], input_sha256: str,
) -> Extraction:
    available_media = {image.media_id for image in packet.images}
    rows = {
        post.record_id: PostExtraction(
            record_id=post.record_id, items=[],
            images=[ImageReading(media_id=media.media_id, status="not_read")
                    for media in post.media if media.media_id in available_media],
        )
        for post in packet.records
    }
    for index, item in enumerate(output.items, start=1):
        segment_ids = list(dict.fromkeys(item.segment_ids))
        if not all(segment_id in passages for segment_id in segment_ids):
            raise ValueError(f"逐帖结果第 {index} 项引用了不存在的片段编号。")
        evidence = [passages[segment_id] for segment_id in segment_ids]
        record_id = evidence[0].record_id
        if any(reference.record_id != record_id for reference in evidence):
            raise ValueError(f"逐帖结果第 {index} 项引用了不同帖子的片段。")
        row = rows[record_id]
        row.items.append(ExtractItem(
            item_id=f"{record_id}-{len(row.items) + 1}", category=item.category, text=item.text, evidence=evidence,
        ))
    return Extraction(input_sha256=input_sha256, posts=list(rows.values()))
