import os
from collections import Counter
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from .x_archive_models import ImportResult

FIELD_MAPPING = [
    ("post_id", "monitored_account", "Excel 中填写的是监控账号。真正的帖子 ID 来自具体原帖链接。"),
    ("author", "author_display_name", "保留存档中的显示名称。空值留空。"),
    ("posted_at", "posted_date / posted_date_raw", "保存日期和原始日期值。两位年份按 2000–2099 年解析。"),
    ("content", "content / text_origin_status", "保留正文。来源类型未确认时记为 unknown_manual_entry。"),
    ("source_url", "source_url / post_id / source_author_handle", "识别帖子链接和链接账号。主页链接保留但没有帖子 ID。"),
    ("photo", "media", "按原始顺序记录图片文件名、所在行和可用状态。"),
    ("quoted_content", "quoted_content / quoted_text_origin_status", "独立保留引用存档文字。"),
    ("quoted_url", "quoted_url / quoted_post_id / quoted_author_handle", "独立记录引用链接及其解析结果。"),
]


def row_ranges(rows: list[int]) -> str:
    groups: list[list[int]] = []
    for row in sorted(set(rows)):
        if groups and row == groups[-1][-1] + 1:
            groups[-1].append(row)
        else:
            groups.append([row])
    return "、".join(str(group[0]) if len(group) == 1 else f"{group[0]}–{group[-1]}" for group in groups)


def markdown_text(value: str) -> str:
    return value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render_report(result: ImportResult) -> str:
    posts = result.posts
    dates = Counter(post.posted_date.isoformat() if post.posted_date else "缺失或无效" for post in posts)
    links = Counter(post.source_url_status for post in posts)
    post_ids = {post.post_id for post in posts if post.post_id is not None}
    media = [image for post in posts for image in post.media]
    accounts = {post.monitored_account.casefold() for post in posts if post.monitored_account}
    quote_links = sum(post.quoted_url_status == "status" for post in posts)
    quote_bodies = sum(post.quoted_content is not None for post in posts)
    verified = sum(post.source_verification == "verified" for post in posts)
    media_count = Counter(image.availability for image in media)

    lines = [
        "# AlphaLens 数据质量报告",
        "",
        f"输入工作簿为 {markdown_text(result.source_file)}，工作表为 {markdown_text(result.sheet)}。",
        f"工作簿 SHA-256 为 `{result.workbook_sha256}`。",
        "",
        "## 导入结果",
        "",
        "| 指标 | 数量 |",
        "| --- | ---: |",
        f"| 表头下扫描行数 | {result.data_rows} |",
        f"| 有正文并保留的存档记录 | {len(posts)} |",
        f"| 空白、占位或无正文行 | {result.data_rows - len(posts)} |",
        f"| Excel 中有正文样本的监控账号 | {len(accounts)} |",
        f"| 含具体原帖链接的记录 | {links['status']} |",
        f"| 不同的原帖 ID | {len(post_ids)} |",
        f"| 只有主页链接的记录 | {links['profile']} |",
        f"| 原帖链接为空的记录 | {links['missing']} |",
        f"| 其他路径或格式无效的原帖链接 | {links['other_x_path'] + links['invalid']} |",
        f"| 已独立核验来源的记录 | {verified} |",
        f"| 含具体引用帖链接的记录 | {quote_links} |",
        f"| 含引用存档文字的记录 | {quote_bodies} |",
        f"| 图片路径条目 | {len(media)} |",
        f"| 项目内匹配且可读取的图片条目 | {media_count['available']} |",
        f"| 工作簿包内嵌媒体文件 | {result.embedded_media_files} |",
        "",
        "### 原始日期分布",
        "",
        "| 存档日期 | 记录数 |",
        "| --- | ---: |",
        *[f"| {label} | {count} |" for label, count in sorted(dates.items())],
        "",
        "日期以 Excel 的人工记录为准。准确发帖时刻、采集时刻和分析时刻缺失时保留空值。",
        "链接仅通过本地格式解析。帖文真伪、作者身份和内容一致性均需独立核对。",
        "",
        "## 字段映射",
        "",
        "| Excel 字段 | 输出字段 | 处理方式 |",
        "| --- | --- | --- |",
        *[f"| `{source}` | `{target}` | {description} |" for source, target, description in FIELD_MAPPING],
        "",
        "## 待核对事项",
        "",
        "| Excel 行号 | 发现 | 建议 |",
        "| --- | --- | --- |",
    ]
    grouped: dict[tuple[str, str, str], list[int]] = {}
    for issue in result.issues:
        key = issue.code, issue.detail, issue.recommendation
        grouped.setdefault(key, []).extend(issue.excel_rows)
    for (_, detail, recommendation), rows in sorted(grouped.items(), key=lambda item: min(item[1])):
        lines.append(f"| {row_ranges(rows)} | {markdown_text(detail)} | {markdown_text(recommendation)} |")
    if not grouped:
        lines.append("| 无 | 未检测到行级问题 | 仍需独立核验原帖和文字。 |")

    if result.relations:
        labels = {
            "shared_post_id": "原帖 ID 相同",
            "identical_content": "正文重复",
            "numbered_thread_candidate": "带编号的线程候选",
            "archive_quote": "可关联到存档中的引用对象（首行为引用方）",
        }
        lines.extend([
            "", "## 可关联记录", "",
            "| 关系 | Excel 行号 |",
            "| --- | --- |",
        ])
        for relation in result.relations:
            rows = " → ".join(map(str, relation.excel_rows)) if relation.kind == "archive_quote" else row_ranges(relation.excel_rows)
            lines.append(f"| {labels[relation.kind]} | {rows} |")

    if media:
        lines.extend([
            "", "## 图片文件检查", "",
            "| Excel 行号 | 顺序 | 原始文件名 | 检查结果 |",
            "| --- | ---: | --- | --- |",
        ])
        statuses = {
            "available": "项目内可读取", "filename_match": "待核对同名文件",
            "missing": "文件缺失", "outside_archive": "存在于项目外", "conflict": "同名文件冲突",
            "unreadable": "无法读取", "invalid_file": "文件格式异常", "unsupported_extension": "扩展名不受支持",
        }
        for image in media:
            lines.append(f"| {image.excel_row} | {image.position} | {markdown_text(image.original_filename)} | {statuses[image.availability]} |")
    lines.extend([
        "", "公开路径为空。图片仍保存在原始目录，归档结果未发布到网页。", "",
    ])
    return "\n".join(lines)


def atomic_write(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, prefix=".import-", delete=False) as temporary:
        temp_path = Path(temporary.name)
        try:
            temporary.write(contents)
            temporary.close()
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def write_outputs(result: ImportResult, output_dir: Path, report_path: Path) -> Path:
    content = (result.model_dump_json(indent=2) + "\n").encode("utf-8")
    report = render_report(result).encode("utf-8")
    output_dir = output_dir.resolve()
    batch = sha256(content).hexdigest()
    snapshot = output_dir / "imports" / batch / "posts.json"
    snapshot.parent.parent.mkdir(parents=True, exist_ok=True)
    with (snapshot.parent.parent / ".lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock, fcntl.LOCK_EX)

        if snapshot.exists():
            if snapshot.read_bytes() != content:
                raise ValueError("历史快照内容与其校验值不一致。请先恢复该快照。")
        else:
            atomic_write(snapshot, content)
        atomic_write(report_path.resolve(), report)
        atomic_write(output_dir / "posts.json", content)
    return snapshot.parent

