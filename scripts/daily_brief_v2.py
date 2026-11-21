"""Generate, validate and archive V2 editions alongside the legacy briefs."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .brief_models import DailyBrief, Extraction, InputPacket
from .brief_pipeline import (
    PROJECT, Prompt, coverage, encode, evidence_index, fingerprint, markdown_text, read_prompts, validate_extraction,
)
from .daily_brief_models import BriefDraft, DailyBriefV2, LeadInsight
from .research_signal_ranking import rank_signals, signal_items
from .x_archive_output import atomic_write

PROMPT_VERSION = "daily_brief_v2.md"


def read_editorial_prompt() -> Prompt:
    text = (PROJECT / "pipeline" / "prompts" / PROMPT_VERSION).read_text(encoding="utf-8")
    return Prompt(PROMPT_VERSION, text, BriefDraft.model_json_schema())


def validate_draft(draft: BriefDraft, index: dict) -> None:
    event_keys = [signal.event_key for signal in draft.candidates]
    theme_keys = [theme.theme_key for theme in draft.research_themes]
    if len(event_keys) != len(set(event_keys)) or len(theme_keys) != len(set(theme_keys)):
        raise ValueError("相同事件或主题需要先合并。")
    if draft.lead_signal_key and draft.lead_signal_key not in event_keys:
        raise ValueError("核心观察引用了不存在的候选信号。")

    def check(ids: list[str], label: str) -> None:
        if len(ids) != len(set(ids)) or set(ids) - index.keys():
            raise ValueError(f"{label}包含重复或不存在的证据编号。")

    if draft.lead_insight:
        check(draft.lead_insight.item_ids, "核心观察")
        lead_signal = next((signal for signal in draft.candidates if signal.event_key == draft.lead_signal_key), None)
        candidate_ids = {key for signal in draft.candidates for key in signal_items(signal)}
        lead_ids = set(draft.lead_insight.item_ids)
        if not lead_signal or not lead_ids & set(signal_items(lead_signal)) or not lead_ids <= candidate_ids:
            raise ValueError("核心观察必须引用对应候选信号的证据。")

    for signal in draft.candidates:
        for ids in (signal.what_happened, signal.bull_case, signal.bear_case):
            check(ids, signal.event_key)
            if any(index[key]["category"] == "inference" for key in ids):
                raise ValueError(f"{signal.event_key} 的来源陈述或支持／反方证据不能使用模型推断。")
        if set(signal.what_happened + signal.bull_case) & set(signal.bear_case):
            raise ValueError(f"{signal.event_key} 的支持与反方证据重叠。")

    for theme in draft.research_themes:
        check(theme.item_ids, theme.theme_key)
        check(theme.conflicting_item_ids, theme.theme_key)
        if theme.conflicting_item_ids and (
            len(theme.conflicting_item_ids) < 2 or not set(theme.conflicting_item_ids) <= set(theme.item_ids)
            or any(index[key]["category"] == "inference" for key in theme.conflicting_item_ids)
        ):
            raise ValueError(f"{theme.theme_key} 的观点冲突需要至少两项主题内的来源证据。")

    update_keys = set()
    for update in draft.other_updates:
        check([update.item_id], update.title)
        if update.record_id in update_keys or not any(
            ref["record_id"] == update.record_id for ref in index[update.item_id]["citations"]
        ):
            raise ValueError("其他信息必须引用对应存档，且同一存档只能出现一次。")
        update_keys.add(update.record_id)


def request_editorial(provider, packet: InputPacket, extraction: Extraction) -> BriefDraft:
    """Use the existing OpenRouter transport and restrict the output to known evidence."""
    validate_extraction(packet, extraction)
    index = evidence_index(packet, extraction)
    if not index:
        return BriefDraft(lead_signal_key=None, lead_insight=None, candidates=[], research_themes=[], other_updates=[],
                          limitations=["当日未提取到可用证据。"])
    prompt = read_editorial_prompt()
    schema = deepcopy(prompt.schema)
    definitions = schema["$defs"]
    for name, fields in (
        ("SignalCandidate", ("what_happened", "bull_case", "bear_case")),
        ("ResearchTheme", ("item_ids", "conflicting_item_ids")),
        ("LeadInsight", ("item_ids",)),
    ):
        for field in fields:
            definitions[name]["properties"][field]["items"]["enum"] = sorted(index)
    definitions["OtherUpdate"]["properties"]["item_id"]["enum"] = sorted(index)
    constrained = replace(prompt, schema=schema)
    data = {
        "report_date": packet.date.isoformat(),
        "allowed_item_ids": sorted(index),
        "data_coverage": coverage(packet),
        "evidence": {key: {**item, "citations": [
            {field: value for field, value in ref.items() if field != "source_url"}
            for ref in item["citations"]
        ]} for key, item in index.items()},
    }
    draft = provider.request_structured(constrained, "alphalens_daily_brief_v2", data, BriefDraft, 16000)
    try:
        validate_draft(draft, index)
    except ValueError as exc:
        retry = replace(constrained, text=constrained.text + "\n按 validation_error 修正上次回复并返回完整结果。")
        draft = provider.request_structured(retry, "alphalens_daily_brief_v2", {**data, "validation_error": str(exc)}, BriefDraft, 16000)
        validate_draft(draft, index)
    return draft


def build_report(
    packet: InputPacket, extraction: Extraction, draft: BriefDraft, mode: str, model: str, generated_at: datetime,
) -> DailyBriefV2:
    validate_extraction(packet, extraction)
    index = evidence_index(packet, extraction)
    validate_draft(draft, index)
    ranked = rank_signals(draft.candidates, index)
    core = [item for item in ranked if item.priority == "core"]
    picked = next((item for item in core if item.event_key == draft.lead_signal_key), core[0] if core else None)
    lead = None
    if picked:
        core_ids = {key for signal in core for key in signal_items(signal)}
        if picked.event_key == draft.lead_signal_key and draft.lead_insight:
            if set(draft.lead_insight.item_ids) <= core_ids:
                lead = draft.lead_insight
        lead = lead or LeadInsight(
            title=picked.title, explanation=picked.investment_implication, related_sectors=picked.related_sectors,
            related_tickers=picked.related_tickers, item_ids=picked.what_happened,
        )
    selected = {record_id for item in core for record_id in item.source_post_ids}
    return DailyBriefV2(
        report_date=packet.date, generated_at=generated_at, generation_mode=mode, prompt_version=PROMPT_VERSION,
        model_name=model, input_post_ids=[post.record_id for post in packet.records], data_coverage=coverage(packet),
        lead_insight=lead, top_signals=core, research_themes=draft.research_themes,
        other_updates=[item for item in draft.other_updates if item.record_id not in selected],
        limitations=draft.limitations, ranked_signals=ranked,
        source_verification_summary={
            state: sum(post.source_verification == state for post in packet.records)
            for state in ("verified", "pending", "missing")
        },
        input_sha256=fingerprint(packet), extraction_sha256=fingerprint(extraction),
    )


def render_markdown(report: DailyBriefV2, index: dict) -> str:
    mode = "OpenRouter 生成" if report.generation_mode == "api" else "Codex 本地回复回放"
    lines = [f"# AlphaLens {report.report_date} 每日投研简报", "", f"生成方式 {mode}", ""]

    def cites(ids: list[str]) -> str:
        return " ".join(f"[{key}](#evidence-{key})" for key in ids)

    labels = {"fact": "事实性陈述", "opinion": "作者观点", "inference": "研究推断"}

    def statements(ids: list[str]) -> list[str]:
        return [f"- **{labels[index[key]['category']]}**  {markdown_text(index[key]['text'])} {cites([key])}"
                for key in ids]

    if report.lead_insight:
        lead = report.lead_insight
        lines += ["## 今日核心观察", "", f"**{markdown_text(lead.title)}**", "",
                  markdown_text(lead.explanation), "", cites(lead.item_ids), ""]
    for signal in report.top_signals:
        lines += [f"## {markdown_text(signal.title)}", "", "### 发生了什么", "", *statements(signal.what_happened), "",
                  "### 为什么重要", "", markdown_text(signal.why_it_matters), "",
                  "### 投资研究含义", "", markdown_text(signal.investment_implication), "",
                  "### 风险与反方观点", "", markdown_text(signal.risks), "",
                  ("反方证据 " + cites(signal.bear_case)) if signal.bear_case else "本次样本未提供反方证据。", "",
                  "### 下一步验证", "", markdown_text(signal.next_research_action), "",
                  "### 支持证据", "", cites(signal.bull_case), "",
                  f"入选依据 {markdown_text(signal.selection_reason)}", ""]
    if report.research_themes:
        lines += ["## 行业主题", ""]
        for theme in report.research_themes:
            lines += [f"- **{markdown_text(theme.title)}**  {markdown_text(theme.current_observation)} {cites(theme.item_ids)}"]
        lines.append("")
    if report.other_updates:
        lines += ["## 其他值得关注的信息", ""]
        for update in report.other_updates:
            lines.append(f"- {markdown_text(update.title)} {cites([update.item_id])}")
        lines.append("")
    lines += ["## 证据与生成方法", "", f"收录 {report.data_coverage.record_count} 条存档。",
              f"模型 {markdown_text(report.model_name)} · Prompt {report.prompt_version} · {report.generated_at.isoformat()}", ""]
    lines += [f"- {markdown_text(note)}" for note in report.limitations]
    for key, item in index.items():
        lines += ["", f'<a id="evidence-{key}"></a>', f"### {labels[item['category']]} · {key}", "",
                  markdown_text(item["text"]), ""]
        for ref in item["citations"]:
            verified = "来源已核验" if ref["source_verification"] == "verified" else "来源待核实"
            url = ref["source_url"] if ref["source_post_id"] else None
            lines += [f"- 存档第 {ref['excel_row']} 行 · {verified}" + (f" · <{url}>" if url else ""),
                      "  " + markdown_text(ref.get("excerpt", ref.get("media_id", "")))]
    return "\n".join(lines) + "\n"


def archive_edition(
    root: Path, packet: InputPacket, extraction: Extraction, draft: BriefDraft, mode: str, model: str,
    extract_prompt: Prompt | None = None,
) -> Path:
    timestamp = datetime.now(timezone.utc)
    report = build_report(packet, extraction, draft, mode, model, timestamp)
    prompt = read_editorial_prompt()
    extract_prompt = extract_prompt or read_prompts()[0]
    identity = {
        "date": packet.date.isoformat(), "input_sha256": report.input_sha256,
        "extraction_sha256": report.extraction_sha256, "draft_sha256": fingerprint(draft),
        "report_sha256": fingerprint(report.model_dump(mode="json", exclude={"generated_at"})),
        "prompt_sha256": fingerprint(prompt.text), "schema_sha256": fingerprint(DailyBriefV2.model_json_schema()),
        "draft_schema_sha256": fingerprint(prompt.schema),
        "extract_prompt": extract_prompt.version().model_dump(),
    }
    run_id = fingerprint(identity)
    parent = root / "v2" / packet.date.isoformat()
    target = parent / run_id
    if target.exists():
        read_edition(target)
        return target
    parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".daily-v2-", dir=parent) as folder:
        staged = Path(folder) / "complete"
        for name, body in (
            ("input.json", encode(packet)), ("extraction.json", encode(extraction)), ("editorial-draft.json", encode(draft)),
            ("brief.json", encode(report)), ("brief.md", render_markdown(report, evidence_index(packet, extraction)).encode("utf-8")),
            ("edition.json", encode({"run_id": run_id, **identity})),
            (PROMPT_VERSION, prompt.text.encode("utf-8")), ("brief.schema.json", encode(DailyBriefV2.model_json_schema())),
            ("draft.schema.json", encode(prompt.schema)), (extract_prompt.name, extract_prompt.text.encode("utf-8")),
            ("extraction.schema.json", encode(extract_prompt.schema)),
        ):
            atomic_write(staged / name, body)
        try:
            staged.rename(target)
        except OSError:
            if not target.is_dir():
                raise
            read_edition(target)
    return target


def read_edition(directory: Path) -> tuple[dict, InputPacket, Extraction, DailyBriefV2]:
    meta = json.loads((directory / "edition.json").read_bytes())
    packet = InputPacket.model_validate_json((directory / "input.json").read_bytes())
    extraction = Extraction.model_validate_json((directory / "extraction.json").read_bytes())
    draft = BriefDraft.model_validate_json((directory / "editorial-draft.json").read_bytes())
    report = DailyBriefV2.model_validate_json((directory / "brief.json").read_bytes())
    extract_contract = meta["extract_prompt"]
    extract_prompt = Prompt(extract_contract["name"],
                            (directory / extract_contract["name"]).read_text(encoding="utf-8"),
                            json.loads((directory / "extraction.schema.json").read_bytes()))
    if (
        directory.name != meta["run_id"] or fingerprint({key: value for key, value in meta.items() if key != "run_id"}) != meta["run_id"]
        or fingerprint(draft) != meta["draft_sha256"]
        or (meta["date"], meta["input_sha256"], meta["extraction_sha256"]) !=
        (packet.date.isoformat(), report.input_sha256, report.extraction_sha256)
        or fingerprint(report.model_dump(mode="json", exclude={"generated_at"})) != meta["report_sha256"]
        or fingerprint((directory / PROMPT_VERSION).read_text(encoding="utf-8")) != meta["prompt_sha256"]
        or fingerprint(json.loads((directory / "brief.schema.json").read_bytes())) != meta["schema_sha256"]
        or fingerprint(json.loads((directory / "draft.schema.json").read_bytes())) != meta["draft_schema_sha256"]
        or extract_prompt.version().model_dump() != extract_contract
        or build_report(packet, extraction, draft, report.generation_mode, report.model_name, report.generated_at) != report
    ):
        raise ValueError("日报 V2 归档校验值不一致。")
    return meta, packet, extraction, report


def preview_data(meta: dict, packet: InputPacket, extraction: Extraction, report: DailyBriefV2) -> dict:
    return {
        "date": packet.date.isoformat(), "run_id": meta["run_id"], "mode": report.generation_mode,
        "provider": "openrouter-chat-completions" if report.generation_mode == "api" else "local-reply",
        "model": report.model_name, "generated_at": report.generated_at.isoformat(),
        "input_sha256": report.input_sha256, "extraction_sha256": report.extraction_sha256,
        "extract_prompt": meta["extract_prompt"]["name"], "report_prompt": report.prompt_version,
        "coverage": report.data_coverage.model_dump(),
        "records": [{"record_id": post.record_id, "excel_row": post.excel_row,
                     "source_verification": post.source_verification} for post in packet.records],
        "image_states": {status: sum(image.status == status for row in extraction.posts for image in row.images)
                         for status in ("not_read", "unreadable", "readable")},
        "brief": DailyBrief(date=packet.date, input_sha256=report.input_sha256, extraction_sha256=report.extraction_sha256,
                            summary=None, events=[], themes=[], hypotheses=[], questions=[], risks=[]).model_dump(
                                mode="json", exclude={"schema_version", "date", "input_sha256", "extraction_sha256"}),
        "evidence": evidence_index(packet, extraction),
        "daily_v2": report.model_dump(mode="json", exclude={"ranked_signals"}),
    }
