"""Normalize a manually saved X workbook without network access."""

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import ValidationError

from .x_archive_media import image_names, inspect_image
from .x_archive_models import ImportResult, Issue, Post, Relation, XLink
from .x_archive_output import write_outputs

PROJECT = Path(__file__).resolve().parents[1]
COLUMNS = ("post_id", "author", "posted_at", "content", "source_url", "photo", "quoted_content", "quoted_url")
HANDLE = r"[A-Za-z0-9_]{1,15}"
X_HOSTS = {"x.com", "twitter.com", "www.x.com", "www.twitter.com", "mobile.x.com", "mobile.twitter.com"}
PART_NUMBER = re.compile(r"\(\s*([0-9]{1,2})\s*/\s*([0-9]{1,2})\s*\)\s*$")


def text(value: object) -> str | None:
    return (str(value).strip() or None) if value is not None else None


def body(value: object) -> str | None:
    return str(value) if text(value) is not None else None


def parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = text(value)
    parts = re.fullmatch(r"([0-9]{2}|[0-9]{4})([-./])([0-9]{1,2})\2([0-9]{1,2})", value or "")
    if parts is None:
        return None
    year, _, month, day = parts.groups()
    try:
        return date(int(year) + (2000 if len(year) == 2 else 0), int(month), int(day))
    except ValueError:
        return None


def classify_url(value: str | None) -> XLink:
    if value is None:
        return XLink(kind="missing")
    if re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return XLink(kind="invalid")
    try:
        url = urlsplit(value)
        if url.scheme not in {"https", "http"} or url.netloc.lower() not in X_HOSTS:
            return XLink(kind="invalid")
    except ValueError:
        return XLink(kind="invalid")

    status = re.fullmatch(
        rf"/(?P<handle>{HANDLE}|i/web)/status/(?P<id>[1-9][0-9]*)"
        r"(?:/(?:photo|video)/[1-9][0-9]*)?/?",
        url.path,
    )
    if status:
        handle, post_id = status.group("handle", "id")
        author = None if handle.casefold() in {"i", "i/web"} else f"@{handle}"
        prefix = handle if author else "i/web"
        return XLink(
            kind="status", url=f"https://x.com/{prefix}/status/{post_id}",
            post_id=post_id, author_handle=author,
        )

    if re.fullmatch(rf"/{HANDLE}/?", url.path) and url.path.strip("/").casefold() not in {
        "home", "explore", "search", "i", "compose", "settings", "notifications", "messages", "login", "intent",
    }:
        return XLink(kind="profile", url=f"https://x.com/{url.path.strip('/')}")
    return XLink(kind="other_x_path")


def audit_rows(workbook_path: Path, sheet: str) -> ImportResult:
    workbook_path = workbook_path.resolve(strict=True)
    workbook_bytes = workbook_path.read_bytes()
    with ZipFile(BytesIO(workbook_bytes)) as package:
        embedded_media = sum(
            name.startswith("xl/media/") and not name.endswith("/") for name in package.namelist()
        )
    workbook = load_workbook(BytesIO(workbook_bytes), keep_links=False)
    try:
        if sheet not in workbook.sheetnames:
            raise ValueError(f"找不到工作表 {sheet}。可用工作表为 {', '.join(workbook.sheetnames)}")
        worksheet = workbook[sheet]
        headers = [text(cell.value) for cell in worksheet[1]]
        missing = [column for column in COLUMNS if headers.count(column) != 1]
        if missing:
            raise ValueError(f"以下列缺失或重复：{'、'.join(missing)}")
        indices = {column: headers.index(column) for column in COLUMNS}
        rows = []
        issues: list[Issue] = []
        for row, cells in enumerate(worksheet.iter_rows(min_row=2), start=2):
            values: dict[str, object] = {}
            for column, index in indices.items():
                cell = cells[index]
                if cell.data_type == "f":
                    issues.append(Issue(
                        code="formula_cell", excel_rows=[row], detail=f"{column} 列为公式",
                        recommendation="核对原表后填写静态值。导入跳过公式。",
                    ))
                    values[column] = None
                    continue
                values[column] = cell.value
                if column in {"source_url", "quoted_url"} and cell.hyperlink and cell.hyperlink.target:
                    target = cell.hyperlink.target
                    displayed = text(cell.value)
                    if displayed and "://" in displayed and displayed != target:
                        issues.append(Issue(
                            code="hyperlink_conflict", excel_rows=[row],
                            detail=f"{column} 列显示链接与实际超链接不同，本次采用实际超链接",
                            recommendation="核对显示内容和超链接目标。",
                        ))
                    values[column] = target
            rows.append(values)
    finally:
        workbook.close()

    posts = []
    for row, values in enumerate(rows, start=2):
        post = normalize_row(values, workbook_path, sheet, row, issues)
        if post is not None:
            posts.append(post)
    relations = relate_records(posts, issues)
    return ImportResult(
        source_file=workbook_path.name,
        sheet=sheet,
        workbook_sha256=sha256(workbook_bytes).hexdigest(),
        data_rows=len(rows),
        embedded_media_files=embedded_media,
        posts=posts,
        relations=relations,
        issues=issues,
    )


def normalize_row(
    values: dict[str, object], workbook_path: Path, sheet: str, row: int, issues: list[Issue],
) -> Post | None:
    def warn(code: str, detail: str, recommendation: str) -> None:
        issues.append(Issue(code=code, excel_rows=[row], detail=detail, recommendation=recommendation))

    content = body(values["content"])
    if content is None:
        has_other_data = any(
            text(values[column]) is not None for column in COLUMNS if column not in {"posted_at", "content"}
        )
        if has_other_data:
            warn("missing_content", "无正文但填有其他资料，原样保留在工作簿",
                 "补上原帖存档文字，或核实该行是否为图片或引用附件。")
        else:
            warn("placeholder_row", "空白或仅填日期", "保留原表，后续填入正文后再导入。")
        return None

    monitored = text(values["post_id"])
    if monitored and re.fullmatch(rf"@?{HANDLE}", monitored):
        monitored = f"@{monitored.lstrip('@')}"
    elif monitored:
        warn("invalid_monitored_account", "监控账号格式无法识别", "核对 Excel 的 post_id 列，填入监控账号。")
        monitored = None
    else:
        warn("missing_monitored_account", "未填写监控账号", "依据采集记录确认账号。原帖链接作者已另外保留。")

    author = text(values["author"])
    if author is None:
        warn("missing_author_display_name", "未填写作者显示名称", "核对采集时的作者显示名称。")

    original_date = text(values["posted_at"])
    posted_date = parse_date(values["posted_at"])
    if posted_date is None:
        warn("invalid_date" if original_date else "missing_date", "日期无效" if original_date else "日期缺失",
             "对照原始记录填写有效日期。原表日期保留在 posted_date_raw。")

    original_url = text(values["source_url"])
    source = classify_url(original_url)
    if source.kind != "status":
        details = {
            "missing": ("missing_source_url", "原帖 URL 缺失"),
            "profile": ("profile_only_source", "只保存了账号主页"),
            "other_x_path": ("non_status_source_url", "X 链接路径未指向具体帖子"),
            "invalid": ("invalid_source_url", "原帖 URL 格式无效或域名不受支持"),
        }
        code, detail = details[source.kind]
        warn(code, detail, "核对采集记录并补充包含 /status/数字 的原帖链接。")
    if original_url and original_url.lower().startswith("http://") and source.kind == "status":
        warn("normalized_http_source", "原表链接为 HTTP，输出已规范为 HTTPS",
             "回查时使用 HTTPS 并确认目标帖子。")
    if monitored and source.author_handle and monitored.casefold() != source.author_handle.casefold():
        warn("source_author_mismatch", f"监控账号 {monitored} 与链接账号 {source.author_handle} 不一致",
             "检查是否为转发、引用或录入错误。两种账号保持分别记录。")

    quote_content = body(values["quoted_content"])
    quote = classify_url(text(values["quoted_url"]))
    if quote.kind != "missing" and quote_content is None:
        warn("missing_quoted_content", "保存了引用链接，引用正文为空", "如需分析引用内容，请补存可核对的原文。")
    if quote.kind == "missing" and quote_content is not None:
        warn("missing_quoted_url", "保存了引用正文，引用链接为空", "补充对应引用帖的具体链接。")
    elif quote.kind not in {"missing", "status"}:
        warn("invalid_quoted_url", "引用链接未指向可识别的 X 帖子", "核对引用对象并填写具体帖子链接。")

    references = image_names(text(values["photo"]))
    record_id = "archive-" + uuid5(
        NAMESPACE_URL,
        json.dumps(
            [workbook_path.name, sheet, row, original_date, content], ensure_ascii=False,
        ),
    ).hex
    media = [
        inspect_image(reference, workbook_path.parent, record_id, row, position)
        for position, reference in enumerate(references, start=1)
    ]
    candidate_guidance = {
        "filename_match": ("media_filename_match", "原路径不可用，项目中有同名候选", "核实同名文件是否对应原帖。"),
        "missing": ("missing_image", "文件缺失", "核对 Excel 路径或将原图放入 data/raw/media/。"),
        "outside_archive": ("external_image", "图片只在项目外存在", "保留原文件，并在媒体阶段归档到 data/raw/media/。"),
        "conflict": ("conflicting_image", "原文件与项目中同名文件不一致", "核对两份图片，确认应归档的文件。"),
        "unreadable": ("unreadable_image", "文件无法读取", "检查访问权限和文件完整性。"),
        "invalid_file": ("invalid_image", "文件内容无法验证为其扩展名对应的图片", "检查图片格式和文件完整性。"),
        "unsupported_extension": ("unsupported_image", "扩展名不受支持", "核对原文件为 JPG、JPEG、PNG 或 WebP。"),
    }
    for item in media:
        if item.availability in candidate_guidance:
            code, detail, remedy = candidate_guidance[item.availability]
            warn(code, f"{item.original_filename} · {detail}", remedy)
        stem = Path(item.original_filename).stem
        if source.post_id and re.fullmatch(r"[0-9]{17,20}", stem) and stem != source.post_id:
            warn("image_filename_id_mismatch", f"图片文件名中的数字 {stem} 与原帖链接 ID 不同",
                 "核对图片与对应分帖的原始出处。文件名只作线索。")

    return Post(
        record_id=record_id, excel_row=row,
        post_id=source.post_id, monitored_account=monitored, author_display_name=author,
        source_author_handle=source.author_handle, posted_date=posted_date, posted_date_raw=original_date,
        content=content, source_url=source.url, source_url_status=source.kind,
        source_verification="missing" if source.kind == "missing" else "pending",
        quoted_content=quote_content, quoted_url=quote.url, quoted_url_status=quote.kind,
        quoted_post_id=quote.post_id, quoted_author_handle=quote.author_handle,
        quoted_text_origin_status="unknown_manual_entry" if quote_content else None,
        quoted_source_verification="missing" if quote.kind == "missing" else "pending",
        media=media,
    )


def relate_records(posts: list[Post], issues: list[Issue]) -> list[Relation]:
    by_id: dict[str, list[Post]] = defaultdict(list)
    by_text: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        if post.post_id:
            by_id[post.post_id].append(post)
        by_text[" ".join(post.content.split())].append(post)

    relations: list[Relation] = []

    def relate(kind: str, group: list[Post]) -> None:
        relations.append(Relation(
            kind=kind, record_ids=[post.record_id for post in group],
            excel_rows=[post.excel_row for post in group],
        ))

    def warn(code: str, group: list[Post], detail: str, remedy: str) -> None:
        issues.append(Issue(
            code=code, excel_rows=[post.excel_row for post in group], detail=detail, recommendation=remedy,
        ))

    for group in by_id.values():
        if len(group) < 2:
            continue
        relate("shared_post_id", group)
        detail = "共用原帖 ID，正文有差异" if len({post.content for post in group}) > 1 else "共用原帖 ID"
        warn("duplicate_source_link", group, detail, "逐行核对是否为分帖或错链，确认前保留全部记录。")
        if len({post.posted_date for post in group if post.posted_date is not None}) > 1:
            warn("conflicting_post_dates", group, "同一原帖 ID 的存档日期不一致",
                 "核对原帖发布时间与 Excel 的原始日期口径。")

    for group in by_text.values():
        if len(group) > 1:
            relate("identical_content", group)
            warn("identical_content", group, "正文去空白比较后完全相同", "检查是否为重复录入，保留各行的来源与图片。")

    thread: list[Post] = []
    expected_total = 0
    for post in posts:
        marker = PART_NUMBER.search(unicodedata.normalize("NFKC", post.content))
        number, total = map(int, marker.groups()) if marker else (0, 0)
        if number == 1 and total >= 2 and post.posted_date and post.monitored_account:
            thread, expected_total = [post], total
            continue
        if not thread:
            continue
        previous = thread[-1]
        if (
            number != len(thread) + 1 or total != expected_total or post.excel_row != previous.excel_row + 1
            or previous.posted_date != post.posted_date
            or (post.monitored_account or "").casefold() != (previous.monitored_account or "").casefold()
        ):
            thread = []
            continue
        thread.append(post)
        if number == expected_total:
            relate("numbered_thread_candidate", thread)
            warn("numbered_thread_candidate", thread, f"正文包含连续的 1/{total} 至 {total}/{total} 分帖编号",
                 "可作为待核实线程查看。逐条确认原帖链接后再合组。")
            thread = []

    for post in posts:
        if post.quoted_post_id:
            targets = [target for target in by_id.get(post.quoted_post_id, []) if target.record_id != post.record_id]
            if targets:
                relate("archive_quote", [post, *targets])
    return relations


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 AlphaLens 手动存档的 X 帖子")
    parser.add_argument("--input", type=Path, default=PROJECT / "data/raw/x_posts.xlsx", help="输入 Excel 路径")
    parser.add_argument("--sheet", default="Sheet1", help="工作表名")
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "data/processed", help="标准化 JSON 和快照目录")
    parser.add_argument("--report", type=Path, default=PROJECT / "docs/DATA_QUALITY_REPORT.md", help="质量报告路径")
    args = parser.parse_args()
    try:
        input_path = args.input.resolve(strict=True)
        report_path = args.report.resolve()
        posts_path = (args.output_dir / "posts.json").resolve()
        if report_path == posts_path or input_path in {report_path, posts_path}:
            raise ValueError("输入 Excel、标准化 JSON 和报告必须使用不同路径。")
        if input_path.suffix.lower() != ".xlsx" or report_path.suffix.lower() != ".md":
            raise ValueError("输入须为 .xlsx，报告路径须为 .md。")
        if report_path.is_file() and report_path.samefile(input_path):
            raise ValueError("质量报告与原始工作簿指向同一个文件。")
        result = audit_rows(input_path, args.sheet)
        snapshot = write_outputs(result, args.output_dir, args.report)
    except (OSError, ValueError, ValidationError, BadZipFile, InvalidFileException) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1

    print(f"读取 {result.data_rows} 行，导入 {len(result.posts)} 条有正文记录，记录 {len(result.issues)} 个问题或核对提示。")
    print(f"工作簿版本快照：{snapshot.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

