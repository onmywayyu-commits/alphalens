from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from pydantic import BaseModel

from .brief_models import (
    BRIEF_ARCHIVE_BUCKETS, DailyBrief, Extraction, ImageReading, ImageReference, InputImage, InputPacket,
    PostExtraction, PromptVersion, RunMetadata, TextReference,
)
from .x_archive_models import ImportResult
from .x_archive_output import atomic_write

PROJECT = Path(__file__).resolve().parents[1]


def encode(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def fingerprint(value: object) -> str:
    return sha256(encode(value)).hexdigest()


def prepare_input(archive: bytes, day: date, preview_dir: Path) -> InputPacket:
    result = ImportResult.model_validate_json(archive)
    records = [post for post in result.posts if post.posted_date == day]
    if not records:
        raise ValueError(f"{day} 没有可用存档记录。")
    preview_media = preview_dir / "media"
    if (preview_dir / "dashboard.json").is_file():
        snapshot = json.loads((preview_dir / "dashboard.json").read_bytes())
        if snapshot.get("archive_workbook_sha256") == result.workbook_sha256:
            descriptors = {
                (entry["archive"]["record_id"], picture["media_id"]): picture["preview_path"]
                for entry in snapshot["posts"] for picture in entry["archive"]["media"]
                if picture["preview_path"]
            }
        else:
            descriptors = {}
    else:
        descriptors = {}

    images = []
    for post in records:
        for media in post.media:
            relative = descriptors.get((post.record_id, media.media_id))
            if not isinstance(relative, str) or not relative.startswith("data/archive-media/"):
                continue
            name = relative.removeprefix("data/archive-media/")
            stem, dot, suffix = name.rpartition(".")
            if not dot or suffix not in {"jpg", "png", "webp"} or len(stem) != 64 or set(stem) - set("0123456789abcdef"):
                raise ValueError("媒体预览文件名与校验值格式不符。")
            image = (preview_media / name).resolve()
            if not image.is_relative_to(preview_media.resolve()):
                raise ValueError("预览图片超出媒体目录。")
            if not image.is_file():
                continue
            content = image.read_bytes()
            if sha256(content).hexdigest() != stem:
                raise ValueError(f"图片 {media.media_id} 校验值变化，请重建预览。")
            images.append(InputImage(media_id=media.media_id, local_path="media/" + name, sha256=stem))

    return InputPacket(
        date=day, archive_sha256=sha256(archive).hexdigest(),
        workbook_sha256=result.workbook_sha256, records=records, images=images,
    )


def coverage(packet: InputPacket) -> dict:
    return {
        "record_count": len(packet.records),
        "distinct_post_count": len({post.post_id for post in packet.records if post.post_id}),
        "source_link_count": sum(post.source_url_status == "status" for post in packet.records),
        "verified_source_count": sum(post.source_verification == "verified" for post in packet.records),
        "image_count": len(packet.images),
    }


def validate_extraction(packet: InputPacket, extraction: Extraction) -> None:
    if extraction.input_sha256 != fingerprint(packet):
        raise ValueError("逐帖输出引用了不同的输入快照。")

    posts = {post.record_id: post for post in packet.records}
    ids = [post.record_id for post in extraction.posts]
    if len(ids) != len(posts) or set(ids) != set(posts):
        raise ValueError("逐帖输出必须覆盖当日每条记录且每条只出现一次。")

    media_ids = {image.media_id for image in packet.images}
    item_ids = set()
    for row in extraction.posts:
        post = posts[row.record_id]
        expected_media = {media.media_id for media in post.media} & media_ids
        readings = {image.media_id: image.status for image in row.images}
        if len(readings) != len(row.images) or readings.keys() != expected_media:
            raise ValueError(f"第 {post.excel_row} 行的图片识别状态与输入不一致。")
        for item in row.items:
            if item.item_id in item_ids:
                raise ValueError(f"重复的证据标识 {item.item_id}。")
            item_ids.add(item.item_id)
            for reference in item.evidence:
                if reference.record_id != row.record_id:
                    raise ValueError(f"证据 {item.item_id} 指向其他记录。")
                if isinstance(reference, ImageReference):
                    if readings.get(reference.media_id) != "readable":
                        raise ValueError(f"证据 {item.item_id} 引用了未读取、不可读或不属于该记录的图片。")
                else:
                    archived = post.content if reference.kind == "body" else post.quoted_content
                    if not archived or not reference.excerpt.strip() or reference.excerpt not in archived:
                        raise ValueError(f"证据 {item.item_id} 的引句无法在存档中定位。")


def validate_brief(packet: InputPacket, extraction: Extraction, brief: DailyBrief) -> None:
    if brief.date != packet.date or brief.input_sha256 != extraction.input_sha256:
        raise ValueError("日报的日期或输入快照不匹配。")
    if brief.extraction_sha256 != fingerprint(extraction):
        raise ValueError("日报引用了不同的逐帖提取版本。")

    items = {item.item_id for row in extraction.posts for item in row.items}
    validate_brief_references(brief, items)


def validate_brief_references(brief: DailyBrief, items: set[str]) -> None:
    def check(ids: Sequence[str], field: str) -> None:
        if not set(ids) <= items:
            raise ValueError(f"日报的 {field} 引用了不存在的证据标识。")
        if len(ids) != len(set(ids)):
            raise ValueError(f"日报的 {field} 含有重复的证据标识。")

    if brief.summary:
        check(brief.summary.item_ids, "summary.item_ids")
    for field in ("events", "themes", "questions", "risks"):
        for index, point in enumerate(getattr(brief, field)):
            check(point.item_ids, f"{field}[{index}].item_ids")

    keys = set()
    for index, hypothesis in enumerate(brief.hypotheses):
        if hypothesis.comparison_key in keys:
            raise ValueError("同一日报中的假设标识重复。")
        keys.add(hypothesis.comparison_key)
        check(hypothesis.support_item_ids, f"hypotheses[{index}].support_item_ids")
        check(hypothesis.counter_item_ids, f"hypotheses[{index}].counter_item_ids")
        if set(hypothesis.support_item_ids) & set(hypothesis.counter_item_ids):
            raise ValueError(f"日报的 hypotheses[{index}] 将同一证据同时列为支持与反方证据。")


def report_input(packet: InputPacket, extraction: Extraction) -> dict:
    origins = {}
    for post in packet.records:
        origins[post.record_id] = {
            "excel_row": post.excel_row, "post_id": post.post_id,
            "source_verification": post.source_verification,
            "content_verification": post.content_verification,
            "quoted_post_id": post.quoted_post_id, "quoted_source_verification": post.quoted_source_verification,
        }
    return {
        "date": packet.date.isoformat(),
        "input_sha256": extraction.input_sha256,
        "extraction_sha256": fingerprint(extraction),
        "coverage": coverage(packet),
        "source_status": origins,
        "extraction": extraction.model_dump(mode="json"),
    }


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    schema: dict

    def version(self) -> PromptVersion:
        return PromptVersion(
            name=self.name,
            sha256=sha256(self.text.encode("utf-8")).hexdigest(),
            schema_sha256=fingerprint(self.schema),
        )


def read_prompts() -> tuple[Prompt, Prompt]:
    def load(name: str, model: type[BaseModel]) -> Prompt:
        return Prompt(name, (PROJECT / "prompts" / name).read_text(encoding="utf-8"), model.model_json_schema())
    return load("extract.v1.md", Extraction), load("report.v1.md", DailyBrief)


class BriefProvider(Protocol):
    name: str
    model: str | None

    def extract(self, packet: InputPacket, prompt: Prompt) -> Extraction: ...
    def summarize(self, prepared: dict, prompt: Prompt) -> DailyBrief: ...


class RehearsalProvider:
    name = "offline-rehearsal"
    model = None

    def extract(self, packet: InputPacket, prompt: Prompt) -> Extraction:
        available = {image.media_id for image in packet.images}
        return Extraction(
            input_sha256=fingerprint(packet),
            posts=[
                PostExtraction(
                    record_id=post.record_id, items=[],
                    images=[ImageReading(media_id=media.media_id, status="not_read")
                            for media in post.media if media.media_id in available],
                )
                for post in packet.records
            ],
        )

    def summarize(self, prepared: dict, prompt: Prompt) -> DailyBrief:
        return DailyBrief(
            date=prepared["date"], input_sha256=prepared["input_sha256"],
            extraction_sha256=prepared["extraction_sha256"],
            summary=None, events=[], themes=[], hypotheses=[], questions=[], risks=[],
        )


@dataclass(frozen=True)
class ReplyProvider:
    extraction: Path
    brief: Path
    model: str
    name: str = "local-reply"

    def extract(self, packet: InputPacket, prompt: Prompt) -> Extraction:
        return Extraction.model_validate_json(self.extraction.read_bytes())

    def summarize(self, prepared: dict, prompt: Prompt) -> DailyBrief:
        return DailyBrief.model_validate_json(self.brief.read_bytes())


def markdown_text(text: str) -> str:
    text = " ".join(text.split())
    return text.translate(str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", "[": "&#91;", "]": "&#93;", "\x60": "&#96;"}))


def evidence_index(packet: InputPacket, extraction: Extraction) -> dict:
    posts = {post.record_id: post for post in packet.records}
    result = {}
    for row in extraction.posts:
        for item in row.items:
            cites = []
            for ref in item.evidence:
                post = posts[ref.record_id]
                is_quote = isinstance(ref, TextReference) and ref.kind == "quote"
                cite = {
                    **ref.model_dump(mode="json"),
                    "excel_row": post.excel_row,
                    "source_post_id": post.quoted_post_id if is_quote else post.post_id,
                    "source_verification": post.quoted_source_verification if is_quote else post.source_verification,
                    "source_url": post.quoted_url if is_quote else post.source_url,
                }
                cites.append(cite)
            result[item.item_id] = {"category": item.category, "text": item.text, "citations": cites}
    return result


def render_markdown(packet: InputPacket, extraction: Extraction, brief: DailyBrief, run: RunMetadata) -> str:
    api_label = "OpenRouter 文字分析" if run.provider == "openrouter-chat-completions" else "OpenAI 生成"
    modes = {"rehearsal": "离线流程演练", "replay": "本地回复回放 · 待人工复核", "api": f"{api_label} · 待人工复核"}
    mode = modes[run.mode]
    stats = coverage(packet)
    lines = [
        f"# AlphaLens {packet.date} 投研日报", "", f"**{mode}**", "",
        f"覆盖 {stats['record_count']} 条存档、{stats['distinct_post_count']} 个可识别 X 帖子 ID、"
        f"{stats['image_count']} 张可用图片。独立核验来源 {stats['verified_source_count']} 条。", "",
    ]
    indexes = evidence_index(packet, extraction)

    def item_links(ids: list[str]) -> str:
        return "、".join(f"[{item_id}](#evidence-{item_id})" for item_id in ids)

    if run.mode == "rehearsal":
        lines.extend(["本次生成空的分析栏目，用于核对输入、格式、引用链接和归档。", ""])
    for title, points in (
        ("摘要", [brief.summary] if brief.summary else []), ("关键事件", brief.events), ("核心主题", brief.themes),
        ("待验证问题", brief.questions), ("风险", brief.risks),
    ):
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {markdown_text(point.text)}（{item_links(point.item_ids)}）" for point in points] or ["暂无分析结论。"])
        lines.append("")
    lines.extend(["## 投资假设", ""])
    for item in brief.hypotheses:
        lines.extend([
            f"- {markdown_text(item.statement)}",
            f"  - 支持证据　{item_links(item.support_item_ids)}",
            f"  - 反方证据　{item_links(item.counter_item_ids) or '未收录'}",
            f"  - 待验证　{'、'.join(markdown_text(question) for question in item.questions)}",
        ])
    if not brief.hypotheses:
        lines.append("暂无已验证格式的假设。")

    lines.extend(["", "## 证据索引", ""])
    labels = {"fact": "事实性陈述", "opinion": "作者观点", "inference": "模型推断"}
    for key, item in indexes.items():
        lines.extend([f'<a id="evidence-{key}"></a>', f"### {key} · {labels[item['category']]}", "",
                      markdown_text(item["text"]), ""])
        for cite in item["citations"]:
            detail = markdown_text(cite["excerpt"]) if cite["kind"] != "image" else markdown_text(cite["media_id"])
            verified = " · 来源已核验" if cite["source_verification"] == "verified" else ""
            lines.append(f"- Excel 第 {cite['excel_row']} 行 · {cite['record_id']}{verified} · {detail}")
        lines.append("")
    lines.extend(["", "## 输入存档", ""])
    lines.extend(f"- Excel 第 {post.excel_row} 行 · {post.record_id}" for post in packet.records)
    lines.extend(["", f"运行标识 {run.run_id}", f"逐帖 Prompt {run.extract_prompt.name} · 日报 Prompt {run.report_prompt.name}", ""])
    return "\n".join(lines)


def archive_run(
    root: Path, packet: InputPacket, provider: BriefProvider, mode: str,
    prompts: tuple[Prompt, Prompt] | None = None,
) -> Path:
    extract_prompt, report_prompt = prompts or read_prompts()
    extraction = provider.extract(packet, extract_prompt)
    validate_extraction(packet, extraction)
    prepared = report_input(packet, extraction)
    brief = provider.summarize(prepared, report_prompt)
    validate_brief(packet, extraction, brief)

    versions = {
        "mode": mode, "provider": provider.name, "model": provider.model,
        "input_sha256": fingerprint(packet), "extraction_sha256": fingerprint(extraction),
        "brief_sha256": fingerprint(brief),
        "extract_prompt": extract_prompt.version().model_dump(), "report_prompt": report_prompt.version().model_dump(),
    }
    run_id = fingerprint(versions)
    parent = root / BRIEF_ARCHIVE_BUCKETS[mode] / packet.date.isoformat()
    destination = parent / run_id
    if destination.exists():
        load_run(destination)
        return destination
    metadata = RunMetadata(run_id=run_id, generated_at=datetime.now(timezone.utc), **versions)
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".brief-", dir=parent) as scratch:
        staged = Path(scratch) / "complete"
        for name, payload in (
            ("input.json", encode(packet)), ("extraction.json", encode(extraction)),
            ("report_input.json", encode(prepared)), ("brief.json", encode(brief)), ("run.json", encode(metadata)),
            ("brief.md", render_markdown(packet, extraction, brief, metadata).encode("utf-8")),
            (extract_prompt.name, extract_prompt.text.encode("utf-8")), (report_prompt.name, report_prompt.text.encode("utf-8")),
            ("extraction.schema.json", encode(extract_prompt.schema)), ("brief.schema.json", encode(report_prompt.schema)),
        ):
            atomic_write(staged / name, payload)
        try:
            staged.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
            load_run(destination)
    return destination


def load_run(directory: Path) -> tuple[RunMetadata, InputPacket, Extraction, DailyBrief]:
    metadata = RunMetadata.model_validate_json((directory / "run.json").read_bytes())
    packet = InputPacket.model_validate_json((directory / "input.json").read_bytes())
    extraction = Extraction.model_validate_json((directory / "extraction.json").read_bytes())
    brief = DailyBrief.model_validate_json((directory / "brief.json").read_bytes())
    actual_key = fingerprint(metadata.model_dump(mode="json", exclude={"run_id", "generated_at"}))
    if (
        metadata.run_id != actual_key or directory.name != actual_key
        or metadata.input_sha256 != fingerprint(packet)
        or metadata.extraction_sha256 != fingerprint(extraction)
        or metadata.brief_sha256 != fingerprint(brief)
    ):
        raise ValueError("归档校验值不一致。")
    for version, schema_file in (
        (metadata.extract_prompt, "extraction.schema.json"), (metadata.report_prompt, "brief.schema.json"),
    ):
        body = (directory / version.name).read_bytes()
        schema = json.loads((directory / schema_file).read_bytes())
        if sha256(body).hexdigest() != version.sha256 or fingerprint(schema) != version.schema_sha256:
            raise ValueError("归档的 Prompt 或 Schema 校验值不一致。")
    validate_extraction(packet, extraction)
    validate_brief(packet, extraction, brief)
    return metadata, packet, extraction, brief

