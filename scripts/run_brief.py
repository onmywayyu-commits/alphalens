"""Run locally with py -3 -m scripts.run_brief."""

import argparse
from datetime import date
from getpass import GetPassWarning, getpass
from pathlib import Path
import sys
import warnings

from .brief_models import Extraction
from .brief_pipeline import (
    PROJECT, RehearsalProvider, ReplyProvider, archive_run, encode, evidence_index,
    fingerprint, load_run, prepare_input, read_prompts, report_input, validate_extraction,
)
from .x_archive_output import atomic_write


def prepare(args, packet) -> Path:
    extract_prompt, report_prompt = read_prompts()
    handoff = {
        "input_sha256": fingerprint(packet),
        "extract_prompt": extract_prompt.version().model_dump(),
        "report_prompt": report_prompt.version().model_dump(),
    }
    destination = args.output / "prepared" / packet.date.isoformat() / fingerprint(handoff)
    for name, contents in (
        ("input.json", encode(packet)), ("manifest.json", encode(handoff)),
        (extract_prompt.name, extract_prompt.text.encode("utf-8")), (report_prompt.name, report_prompt.text.encode("utf-8")),
        ("extraction.schema.json", encode(extract_prompt.schema)), ("brief.schema.json", encode(report_prompt.schema)),
    ):
        atomic_write(destination / name, contents)
    if args.extraction:
        extraction = Extraction.model_validate_json(args.extraction.read_bytes())
        validate_extraction(packet, extraction)
        destination = destination / fingerprint(extraction) / "report_input.json"
        atomic_write(destination, encode(report_input(packet, extraction)))
    return destination


def compare(before: Path, after: Path) -> dict:
    old_run, old_packet, old_extraction, old_brief = load_run(before)
    new_run, new_packet, new_extraction, new_brief = load_run(after)
    if old_brief.date >= new_brief.date:
        raise ValueError("请按较早、较晚两个存档日期传入归档目录。")

    old_index = evidence_index(old_packet, old_extraction)
    new_index = evidence_index(new_packet, new_extraction)
    old_hypotheses = {item.comparison_key: item for item in old_brief.hypotheses}
    new_hypotheses = {item.comparison_key: item for item in new_brief.hypotheses}
    rows = []

    def sources(index: dict, item_ids: list[str]) -> set[str]:
        return {
            cite["source_post_id"] for item_id in item_ids for cite in index[item_id]["citations"]
            if cite["source_post_id"]
        }

    for key in sorted(old_hypotheses.keys() | new_hypotheses.keys()):
        old = old_hypotheses.get(key)
        new = new_hypotheses.get(key)
        row = {
            "comparison_key": key,
            "before_statement": old.statement if old else None,
            "after_statement": new.statement if new else None,
            "status": "暂无法判断变化",
            "reason": "两天缺少同口径的假设与可区分来源。",
            "new_support_post_ids": [],
            "new_counter_post_ids": [],
        }
        if old and new and " ".join(old.statement.split()) == " ".join(new.statement.split()):
            previous = sources(old_index, old.support_item_ids + old.counter_item_ids)
            support = sources(new_index, new.support_item_ids)
            counter = sources(new_index, new.counter_item_ids)
            if previous and (support | counter):
                new_support = support - counter - previous
                new_counter = counter - support - previous
                row.update(
                    status="新增可区分来源" if new_support or new_counter else "暂无法判断变化",
                    reason="按 X 帖子 ID 区分新来源，来源及观点仍需复核。" if new_support or new_counter
                    else "已匹配假设，未找到可区分的新增支持或反方来源。",
                    new_support_post_ids=sorted(new_support), new_counter_post_ids=sorted(new_counter),
                )
        rows.append(row)
    changed = any(row["status"] == "新增可区分来源" for row in rows)
    return {
        "schema_version": 1,
        "before": {"date": old_brief.date.isoformat(), "run_id": old_run.run_id, "mode": old_run.mode},
        "after": {"date": new_brief.date.isoformat(), "run_id": new_run.run_id, "mode": new_run.mode},
        "status": "部分假设有新增来源，需人工复核" if changed else "暂无法判断变化",
        "hypotheses": rows,
    }


def prompt_for_api_key() -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        try:
            return getpass("粘贴完整 Secret Key 后按回车（输入不会显示）：")
        except (GetPassWarning, EOFError) as exc:
            raise ValueError("当前终端无法隐藏输入，请在本机 PowerShell 窗口运行。") from exc
        except KeyboardInterrupt:
            raise ValueError("已取消密钥输入。") from None


def main() -> int:
    parser = argparse.ArgumentParser(description="AlphaLens 投研日报的准备、生成、校验与归档")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("prepare", "导出输入、Prompt 和 JSON Schema"),
        ("rehearse", "用存档演练流程，留空分析栏目"),
        ("replay", "校验已有的两段本地 JSON 回复并归档"),
        ("generate", "调用模型，校验并保存指定日期的日报"),
        ("generate-v2", "用 OpenRouter 生成并归档 V2 日报"),
        ("replay-v2", "校验本地逐帖结果及 V2 编辑稿后归档"),
    ):
        option = commands.add_parser(command, help=help_text)
        option.add_argument("--date", required=True, type=date.fromisoformat)
        option.add_argument("--archive", type=Path, default=PROJECT / "data/processed/posts.json")
        option.add_argument("--preview-dir", type=Path, default=PROJECT / "frontend/.local-archive")
        option.add_argument("--output", type=Path, default=PROJECT / "data/reports")
        if command in {"prepare", "replay"}:
            option.add_argument("--extraction", type=Path, required=command == "replay")
        if command == "replay":
            option.add_argument("--brief", type=Path, required=True)
            option.add_argument("--model", required=True, help="离线回复对应的模型或配置名称")
        if command == "generate":
            option.add_argument("--provider", choices=("openai", "openrouter"), default="openai")
        if command in {"generate", "generate-v2"}:
            option.add_argument("--model", help="模型名称，默认使用所选服务的推荐模型")
            option.add_argument("--prompt-key", action="store_true", help="通过终端隐藏输入密钥")
        if command == "replay-v2":
            option.add_argument("--extraction", type=Path, required=True)
            option.add_argument("--draft", type=Path, required=True)
            option.add_argument("--model", required=True, help="本地回复对应的模型或来源")

    connection = commands.add_parser("check-connection", help="检查 API 的 HTTPS 连接，无需密钥")
    connection.add_argument("--provider", choices=("openai", "openrouter"), default="openai")
    diff = commands.add_parser("compare", help="比较两个已归档运行的同口径证据")
    diff.add_argument("--before", type=Path, required=True)
    diff.add_argument("--after", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "check-connection":
        from .openai_brief import API_BASE_URL, check_connection
        from .openrouter_brief import API_BASE_URL as OPENROUTER_URL

        try:
            print(check_connection(OPENROUTER_URL if args.provider == "openrouter" else API_BASE_URL))
        except ValueError as exc:
            print(f"连接检测失败：{exc}", file=sys.stderr)
            return 1
        return 0

    try:
        if args.command == "compare":
            print(encode(compare(args.before, args.after)).decode("utf-8"), end="")
            return 0
        packet = prepare_input(args.archive.read_bytes(), args.date, args.preview_dir)
        if args.command == "prepare":
            destination = prepare(args, packet)
        elif args.command == "generate-v2":
            from .daily_brief_v2 import archive_edition, request_editorial
            from .openrouter_brief import DEFAULT_MODEL, OpenRouterBriefProvider, read_openrouter_prompts

            extract_prompt, _ = read_openrouter_prompts()
            api_key = prompt_for_api_key() if args.prompt_key else None
            with OpenRouterBriefProvider(args.model or DEFAULT_MODEL, args.preview_dir, api_key=api_key) as provider:
                extraction = provider.extract(packet, extract_prompt)
                draft = request_editorial(provider, packet, extraction)
                destination = archive_edition(args.output, packet, extraction, draft, "api", provider.model, extract_prompt)
        elif args.command == "replay-v2":
            from .daily_brief_models import BriefDraft
            from .daily_brief_v2 import archive_edition

            extraction = Extraction.model_validate_json(args.extraction.read_bytes())
            draft = BriefDraft.model_validate_json(args.draft.read_bytes())
            destination = archive_edition(args.output, packet, extraction, draft, "replay", args.model)
        elif args.command == "generate":
            if args.provider == "openrouter":
                from .openrouter_brief import DEFAULT_MODEL, OpenRouterBriefProvider as BriefGenerator
                from .openrouter_brief import read_openrouter_prompts

                prompts = read_openrouter_prompts()
            else:
                from .openai_brief import DEFAULT_MODEL, OpenAIBriefProvider as BriefGenerator

                prompts = None

            api_key = prompt_for_api_key() if args.prompt_key else None
            with BriefGenerator(args.model or DEFAULT_MODEL, args.preview_dir, api_key=api_key) as provider:
                destination = archive_run(args.output, packet, provider, "api", prompts=prompts)
        else:
            provider = RehearsalProvider() if args.command == "rehearse" else ReplyProvider(
                args.extraction, args.brief, args.model,
            )
            destination = archive_run(args.output, packet, provider, "rehearsal" if args.command == "rehearse" else "replay")
    except (OSError, ValueError, KeyError) as exc:
        print(f"日报流程失败：{exc}", file=sys.stderr)
        return 1
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

