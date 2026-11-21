"""Prepare a local-only AlphaLens preview from validated archive rows."""

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path

from pydantic import TypeAdapter

from pipeline.post_analysis_models import PostAnalysisExample
from pipeline.post_analysis import ANALYSIS_DIR, IMAGE_READINGS_NAME, latest_analysis, read_image_readings, read_prompt

from .brief_preview import preview_runs
from .import_x_posts import classify_url
from .x_archive_media import inspect_image
from .x_archive_models import ImportResult
from .x_archive_output import atomic_write

PROJECT = Path(__file__).resolve().parents[1]


def prepare_preview(
    result: ImportResult, raw_dir: Path, overview_config: dict,
    preview_dir: Path, manifest_path: Path, report_dir: Path | None = None,
    analysis_dir: Path | None = None,
) -> tuple[int, int]:
    raw_dir = raw_dir.resolve()
    media_root = raw_dir / "media"
    manifest_entries = []
    posts = []
    examples_path = preview_dir / "post-analysis-examples.json"
    examples = TypeAdapter(dict[str, PostAnalysisExample]).validate_json(examples_path.read_bytes()) if examples_path.is_file() else {}
    prompt = read_prompt() if analysis_dir and analysis_dir.is_dir() else None
    readings = read_image_readings(analysis_dir / IMAGE_READINGS_NAME) if prompt else {}

    for post in result.posts:
        pictures = []
        for media in post.media:
            checked = media
            preview_path = None
            file_digest = None
            if media.local_path and media.availability == "available":
                candidate = raw_dir / media.local_path
                path = candidate.resolve()
                if path.is_relative_to(media_root):
                    checked = inspect_image(str(path), raw_dir, post.record_id, post.excel_row, media.position)
                    content = None
                    if checked.availability == "available":
                        try:
                            content = path.read_bytes()
                        except FileNotFoundError:
                            checked = checked.model_copy(update={"exists": False, "availability": "missing"})
                        except OSError:
                            checked = checked.model_copy(update={"availability": "unreadable"})
                    if content is not None:
                        file_digest = sha256(content).hexdigest()
                        name = file_digest + path.suffix.lower().replace(".jpeg", ".jpg")
                        target = preview_dir / "media" / name
                        if not target.exists() or sha256(target.read_bytes()).hexdigest() != file_digest:
                            atomic_write(target, content)
                        preview_path = "data/archive-media/" + name
                else:
                    checked = media.model_copy(update={"exists": False, "availability": "unreadable"})

            descriptor = {
                "media_id": media.media_id, "original_filename": media.original_filename,
                "position": media.position, "availability": checked.availability,
                "exists": checked.exists, "preview_path": preview_path,
            }
            manifest_entries.append({
                **descriptor, "record_id": post.record_id, "excel_row": post.excel_row,
                "local_path": media.local_path, "public_path": None, "sha256": file_digest,
            })
            pictures.append(descriptor)

        analysis = latest_analysis(analysis_dir, post, readings.get(post.record_id, []), prompt) if prompt else None
        example = None if analysis else examples.get(post.record_id)
        if example:
            used = {key for point in example.analysis.cited_points() for key in point.evidence_ids}
            if used != example.evidence.keys() or any(
                source.record_id != post.record_id or source.kind != "body" or source.excerpt not in post.content
                for source in example.evidence.values()
            ):
                example = None
            else:
                link = classify_url(post.source_url)
                example = example.model_copy(update={
                    "evidence": {
                        key: source.model_copy(update={
                            "source_url": link.url if link.kind == "status" else None,
                            "source_verification": post.source_verification,
                            "content_verification": post.content_verification,
                            "attribution": post.author_display_name or post.source_author_handle,
                        }) for key, source in example.evidence.items()
                    },
                    "media_analysis_status": "not_analyzed" if post.media else "no_media",
                })
        posts.append({
            "post_id": post.post_id, "author": (post.monitored_account or "").removeprefix("@"),
            "source_url": post.source_url, "published_at": post.posted_at, "collected_at": post.collected_at,
            "source_type": "manual", "content": post.content, "is_demo": False,
            "title": None, "summary": None, "industry": None, "companies": [],
            "information_type": None, "relevance": None, "evidence": [],
            **({"post_analysis": analysis.model_dump(mode="json")} if analysis else {}),
            **({"post_analysis_example": example.model_dump(mode="json")} if example else {}),
            "archive": {
                "record_id": post.record_id, "excel_row": post.excel_row, "posted_date": post.posted_date,
                "author_display_name": post.author_display_name, "source_author_handle": post.source_author_handle,
                "source_verification": post.source_verification, "source_url_status": post.source_url_status,
                "content_verification": post.content_verification, "text_origin_status": post.text_origin_status,
                "quoted_content": post.quoted_content, "quoted_url": post.quoted_url,
                "quoted_url_status": post.quoted_url_status, "quoted_author_handle": post.quoted_author_handle,
                "quoted_post_id": post.quoted_post_id,
                "analysis_status": "analyzed" if analysis else post.analysis_status,
                "analysis_at": analysis.generated_at if analysis else post.analysis_at, "media": pictures,
            },
        })

    image_hashes = {item["media_id"]: item["sha256"] for item in manifest_entries if item["sha256"]}
    dashboard = {
        "schema_version": 1, "mode": "research", "updated_at": None,
        "archive_workbook_sha256": result.workbook_sha256,
        "brief_runs": preview_runs(report_dir, result, image_hashes) if report_dir else [],
        "accounts": overview_config["accounts"], "posts": posts, "ideas": [], "reports": [],
        "relations": [relation.model_dump(mode="json") for relation in result.relations],
    }

    def encode(value: object) -> bytes:
        return (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")

    atomic_write(manifest_path, encode({
        "schema_version": 1, "workbook_sha256": result.workbook_sha256, "media": manifest_entries,
    }))
    atomic_write(preview_dir / "dashboard.json", encode(dashboard))
    return len(posts), sum(item["preview_path"] is not None for item in manifest_entries)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成仅用于本机联调的 AlphaLens 存档预览")
    parser.add_argument("--posts", type=Path, default=PROJECT / "data/processed/posts.json")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT / "data/raw")
    parser.add_argument("--analyses", type=Path, default=ANALYSIS_DIR)
    args = parser.parse_args()
    try:
        archive = args.posts.read_bytes()
        result = ImportResult.model_validate_json(archive)
        config = json.loads((PROJECT / "data/processed/dashboard.json").read_text(encoding="utf-8"))
        posts, pictures = prepare_preview(
            result, args.raw_dir, config, PROJECT / "frontend/.local-archive",
            PROJECT / "data/processed/media_manifest.json",
            PROJECT / "data/reports", args.analyses,
        )
    except (OSError, ValueError) as exc:
        print(f"无法生成存档预览：{exc}", file=sys.stderr)
        return 1
    print(f"已准备本机预览：{posts} 条记录，{pictures} 个可读取的图片关联。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

