"""Generate static, traceable research analysis with the existing OpenRouter client."""

import argparse
from contextlib import ExitStack
from datetime import date
from getpass import getpass
import os
from pathlib import Path
import sys

from scripts.brief_pipeline import PROJECT
from scripts.openrouter_brief import DEFAULT_MODEL, OpenRouterBriefProvider
from scripts.x_archive_models import ImportResult

from .post_analysis import ANALYSIS_DIR, IMAGE_READINGS_NAME, analyze_post, read_image_readings, read_prompt
from .post_analysis_models import PostAnalysisDraft


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 OpenRouter 预生成 AlphaLens 单帖投研解读")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--date", type=date.fromisoformat, help="分析该日期的所有存档（YYYY-MM-DD）")
    selection.add_argument("--record-id", help="只分析指定存档")
    selection.add_argument("--row", type=int, action="append", help="按 Excel 行号分析，可重复传入")
    parser.add_argument("--posts", type=Path, default=PROJECT / "data/processed/posts.json")
    parser.add_argument("--output", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--model", default=os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--prompt-key", action="store_true", help="未设置环境变量时在本机终端隐藏输入密钥")
    args = parser.parse_args()

    try:
        archive = ImportResult.model_validate_json(args.posts.read_bytes())
        selected = [
            post for post in archive.posts
            if ((args.date is not None and post.posted_date == args.date)
                or (args.record_id is not None and post.record_id == args.record_id)
                or post.excel_row in (args.row or []))
        ]
        if not selected:
            raise ValueError("没有符合指定条件的存档记录。")
        if len({post.record_id for post in selected}) != len(selected):
            raise ValueError("所选存档存在重复记录 ID。")
        prompt = read_prompt()
        images = read_image_readings(args.output / IMAGE_READINGS_NAME)
    except (ValueError, OSError) as exc:
        print(f"无法准备单帖分析：{exc}", file=sys.stderr)
        return 1

    failures = 0
    with ExitStack() as stack:
        client = None

        def generate(current_prompt, payload):
            nonlocal client
            if client is None:
                key = os.getenv("OPENROUTER_API_KEY", "").strip()
                if not key and args.prompt_key and sys.stdin.isatty():
                    key = getpass("请输入 OpenRouter API Key（输入不会显示）：").strip()
                if not key:
                    raise ValueError("未配置 OPENROUTER_API_KEY。也可在本机终端使用 --prompt-key。")
                client = stack.enter_context(OpenRouterBriefProvider(args.model, args.output, api_key=key))
            return client.request_structured_with_metadata(
                current_prompt, "alphalens_post_analysis", payload, PostAnalysisDraft, 8192,
            )

        for post in selected:
            try:
                item, cached = analyze_post(
                    post, images.get(post.record_id, []), prompt, args.output,
                    OpenRouterBriefProvider.name, args.model, generate,
                )
            except (ValueError, OSError) as exc:
                print(f"第 {post.excel_row} 行分析失败：{exc}", file=sys.stderr)
                if client is None:
                    return 1
                failures += 1
                continue
            status = "复用已保存结果" if cached else "已保存"
            print(f"{status}：第 {post.excel_row} 行 {item.record_id}，模型 {item.model_name}")
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(main())
